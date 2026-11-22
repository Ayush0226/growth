import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import RouteFog from './RouteFog'
import './styles.css'
import './workspace-navigation.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode><BrowserRouter><App /><RouteFog /></BrowserRouter></StrictMode>,
)
