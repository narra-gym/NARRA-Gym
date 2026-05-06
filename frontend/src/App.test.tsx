import React from 'react';
import { render, screen } from '@testing-library/react';
import App from './App';

jest.mock('./components/ShaderBackground', () => () => <div data-testid="shader-background" />);

test('renders the home screen', () => {
  render(<App />);
  expect(screen.getByText(/EmoNest/i)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /Benchmark Mode/i })).toBeInTheDocument();
});
