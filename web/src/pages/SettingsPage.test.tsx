import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import SettingsPage from './SettingsPage';

vi.mock('../api/client', () => ({
  api: { changePassword: vi.fn() },
}));
import { api } from '../api/client';
import { ApiError } from '../api/http';

describe('SettingsPage', () => {
  beforeEach(() => { vi.mocked(api.changePassword).mockReset(); });

  it('submits current and new password and confirms', async () => {
    vi.mocked(api.changePassword).mockResolvedValue({ status: 'ok' } as never);
    render(<SettingsPage />);
    await userEvent.type(screen.getByLabelText(/current password/i), 'Old1!aa');
    await userEvent.type(screen.getByLabelText(/^new password$/i), 'New2!bb');
    await userEvent.type(screen.getByLabelText(/confirm new password/i), 'New2!bb');
    await userEvent.click(screen.getByRole('button', { name: /update password/i }));
    expect(await screen.findByText('Password updated.')).toBeInTheDocument();
    expect(vi.mocked(api.changePassword)).toHaveBeenCalledWith('Old1!aa', 'New2!bb');
  });

  it('blocks submit when confirmation does not match', async () => {
    render(<SettingsPage />);
    await userEvent.type(screen.getByLabelText(/current password/i), 'Old1!aa');
    await userEvent.type(screen.getByLabelText(/^new password$/i), 'New2!bb');
    await userEvent.type(screen.getByLabelText(/confirm new password/i), 'Different!1');
    await userEvent.click(screen.getByRole('button', { name: /update password/i }));
    expect(await screen.findByRole('alert')).toHaveTextContent('New passwords do not match');
    expect(vi.mocked(api.changePassword)).not.toHaveBeenCalled();
  });

  it('shows backend validation errors verbatim', async () => {
    vi.mocked(api.changePassword).mockRejectedValue(
      new ApiError(422, 'must include at least 3 of: lowercase, uppercase, digit, symbol'));
    render(<SettingsPage />);
    await userEvent.type(screen.getByLabelText(/current password/i), 'Old1!aa');
    await userEvent.type(screen.getByLabelText(/^new password$/i), 'short');
    await userEvent.type(screen.getByLabelText(/confirm new password/i), 'short');
    await userEvent.click(screen.getByRole('button', { name: /update password/i }));
    expect(await screen.findByRole('alert')).toHaveTextContent('must include at least 3 of');
  });
});