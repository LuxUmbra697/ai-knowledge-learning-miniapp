import { PropsWithChildren, useEffect, createElement } from 'react'
import { resolveLogin } from './services/api'
import './app.scss'
import { StudioProvider } from './components/StudioProvider'

function App({ children }: PropsWithChildren) {
  useEffect(() => {
    resolveLogin()
  }, [])

  return createElement(StudioProvider, null, children)
}

export default App
