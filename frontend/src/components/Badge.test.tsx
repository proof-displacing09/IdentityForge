import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ModeBadge, StatusBadge } from './Badge'

describe('StatusBadge', () => {
  it('renders PASS with status role', () => {
    render(<StatusBadge status="PASS" />)
    expect(screen.getByRole('status')).toHaveTextContent('PASS')
  })
  it('renders FAIL and SKIPPED distinctly', () => {
    const { rerender } = render(<StatusBadge status="FAIL" />)
    expect(screen.getByRole('status')).toHaveTextContent('FAIL')
    rerender(<StatusBadge status="SKIPPED" />)
    expect(screen.getByRole('status')).toHaveTextContent('SKIPPED / NOT RUN')
  })
})

describe('ModeBadge', () => {
  it('labels offline fixtures honestly', () => {
    render(<ModeBadge mode="DETERMINISTIC OFFLINE FIXTURE" />)
    expect(screen.getByText('DETERMINISTIC OFFLINE FIXTURE')).toBeInTheDocument()
  })
  it('labels real Keycloak distinctly from fixtures', () => {
    render(<ModeBadge mode="LOCAL REAL KEYCLOAK INTEGRATION" />)
    expect(screen.getByText('LOCAL REAL KEYCLOAK INTEGRATION')).toBeInTheDocument()
  })
  // P2-19 (v4): teal is reserved for verified identity. A real
  // Keycloak login gets the teal badge-live class; an offline fixture
  // gets the azure badge-fixture class — never the reverse.
  it('colours real Keycloak teal (verified identity) and fixtures azure', () => {
    const { rerender } = render(<ModeBadge mode="LOCAL REAL KEYCLOAK INTEGRATION" />)
    expect(screen.getByText('LOCAL REAL KEYCLOAK INTEGRATION')).toHaveClass('badge-live')
    rerender(<ModeBadge mode="DETERMINISTIC OFFLINE FIXTURE" />)
    expect(screen.getByText('DETERMINISTIC OFFLINE FIXTURE')).toHaveClass('badge-fixture')
    expect(screen.getByText('DETERMINISTIC OFFLINE FIXTURE')).not.toHaveClass('badge-live')
  })
})
