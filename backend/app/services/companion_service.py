from app.llm import companion_chain as chain
from app.repositories import companion_repository as repository


async def run(context):
    material = await repository.material(context)
    await context.checkpoint('companion_context', {'memory_count': len(material['memories']),
                                                'history_turns': len(material['history']), 'canon_version': material['canon_version']})
    response = await chain.generate(material, context)
    response = chain.validate_reply(response, material)
    await context.checkpoint('companion_validated', {'emotion': response['emotion'], 'memory_references': len(response['used_memory_ids'])})
    return await repository.publish(context, response)
