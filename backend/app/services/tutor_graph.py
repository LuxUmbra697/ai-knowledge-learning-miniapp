"""Bounded LangGraph tutor; MySQL task checkpoints own recovery, not process memory."""
from typing import TypedDict

from fastapi import HTTPException
from langgraph.graph import END, START, StateGraph

from app.llm import tutor_chain
from app.repositories import tutor_repository as repository
from app.services import tutor_service
from app.services.tutor_tools import TutorTools


class TutorState(TypedDict, total=False):
    session: dict
    learning: dict
    review: dict
    evidence: list
    retrieval_status: str
    memory: list
    response: dict


def practice_evidence(source):
    question = source['question']
    options = '\n'.join(f"{item['key']}: {item['text'][:250]}" for item in question.get('options', [])[:8])
    return ('已保存的题目：' + question['stem'][:1000] + '\n选项：\n' + options
            + '\n学生作答：' + '、'.join(source['record']['selected_answers'])[:1000]
            + '\n参考答案：' + '、'.join(question['answer'])[:1000] + '\n参考解析：' + question['explanation'][:1500])


async def run(context):
    session = await repository.get(context.payload['session_id'], context.user_id)
    await tutor_service.validate_session(session, context.user_id)
    config = session['config_json']
    tools = TutorTools(context.user_id, tuple(config['doc_ids']), context)

    async def cached(stage, operation):
        if stage in context.checkpoints:
            return context.checkpoints[stage]
        value = await operation()
        await context.checkpoint(stage, value)
        return value

    async def identify(_state):
        await tutor_service.validate_session(session, context.user_id)
        async def snapshot():
            history = await repository.turns(session['session_id'], context.user_id)
            return [{'student': turn['message'][:500], 'hint': turn['response']['hint'][:400], 'question': turn['response']['question'][:180]}
                    for turn in history[-2:]]
        memory = await cached('tutor_identify', snapshot)
        return {'session': repository.public(session), 'memory': memory}

    async def read_state(_state):
        learning = await cached('tutor_learning', lambda: tools.call('read_learning_state', {}))
        review = await cached('tutor_review', lambda: tools.call('review_queue', {}))
        return {'learning': learning, 'review': review}

    async def retrieve(_state):
        async def fetch():
            query = (config['goal'][:500] + '\n' + context.payload['query'][:499])[:1000]
            result = await tools.call('retrieve_notes', {'query': query})
            if result['status'] == 'failed':
                raise HTTPException(503, '材料检索失败，请稍后重试辅导')
            if config.get('card_id'):
                source = await tutor_service.practice_material(context.user_id, config['card_id'])
                question = source['question']
                content = practice_evidence(source)
                result['evidence'].append({'id': 'P1', 'source_type': 'stored_practice', 'content': content, 'quiz_id': source['quiz_id'],
                                           'question_id': question['id'], 'file_name': '已保存的错题与参考解析',
                                           'verification': 'Generated practice reference, not independently verified facts'})
            return result
        result = await cached('tutor_evidence', fetch)
        return {'evidence': result['evidence'], 'retrieval_status': result['status']}

    async def no_evidence(_state):
        return {'response': {'status': 'no_evidence', 'hint': '本次材料没有足够依据，暂不提供推测性提示。',
                             'question': '你愿意换一份材料，或指出想讨论的段落吗？', 'citations': [], 'diagnosis': None, 'practice': None}}

    async def coach(state):
        material = {'mode': config['mode'], 'goal': config['goal'], 'turn': context.payload['session_version'] + 1,
                    'student_reply': context.payload['query'], 'memory': state['memory'], 'evidence': state['evidence'],
                    'learning': state['learning'], 'due_review_count_sample': len(state['review']['items'])}
        result = await tutor_chain.generate(material, context)
        return {'response': result}

    async def validate(state):
        await tutor_service.validate_session(session, context.user_id)
        result = dict(state['response'])
        if result['status'] != 'no_evidence':
            result = tutor_chain.validate_reply(result, state['evidence'], config['mode'], context.payload['session_version'] + 1)
        proposal = await tools.call('propose_practice', result['practice']) if result.get('practice') else None
        result.update(evidence=state['evidence'], retrieval_status=state['retrieval_status'], practice=proposal,
                      diagnosis_source='model_suggestion_requires_confirmation' if result['diagnosis'] else None,
                      config_version='tutor-graph-v1', memory_turns=len(state['memory']))
        result['tool_summary'] = {'evidence_count': len(state['evidence']), 'learning_concepts': len(state['learning']['concepts']),
                                  'due_review_sample': len(state['review']['items']), 'practice_proposed': proposal is not None,
                                  'fresh_tool_calls': len(tools.calls), 'max_tool_calls': 4}
        await context.checkpoint('tutor_validated', {'status': result['status'], 'citations': len(result['citations']),
                                                    'tools': ['read_learning_state', 'review_queue', 'retrieve_notes'] + (['propose_practice'] if proposal else [])})
        return {'response': result}

    builder = StateGraph(TutorState)
    for name, node in [('identify', identify), ('read_state', read_state), ('retrieve', retrieve), ('coach', coach), ('no_evidence', no_evidence), ('validate', validate)]:
        builder.add_node(name, node)
    builder.add_edge(START, 'identify')
    builder.add_edge('identify', 'read_state')
    builder.add_edge('read_state', 'retrieve')
    builder.add_conditional_edges('retrieve', lambda state: 'coach' if state['evidence'] else 'no_evidence')
    builder.add_edge('coach', 'validate')
    builder.add_edge('no_evidence', 'validate')
    builder.add_edge('validate', END)
    result = await builder.compile().ainvoke({}, {'recursion_limit': 8})
    return await repository.publish(context, result['response'])
