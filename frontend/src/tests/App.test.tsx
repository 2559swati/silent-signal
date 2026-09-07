import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import App from '../App'

describe('App', () => {
  it('renders without crashing and displays the title', () => {
    render(<App />)
    const titleElements = screen.getAllByText(/SilentSignal AI/i)
    expect(titleElements.length).toBeGreaterThanOrEqual(1)
    titleElements.forEach((el) => expect(el).toBeInTheDocument())
  })

  it('renders the primary navigation', () => {
    render(<App />)
    for (const label of ['Dashboard', 'Assets', 'Risk Monitor', 'Explanations', 'Preventive Actions']) {
      expect(screen.getByText(label)).toBeInTheDocument()
    }
  })

  it('shows the pipeline story on the dashboard', () => {
    render(<App />)
    expect(screen.getByText(/From weak signals to preventive action/i)).toBeInTheDocument()
  })
})
