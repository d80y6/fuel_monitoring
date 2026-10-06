import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { notificationApi } from '../api/admin';
import { ErrorCard } from '../components/ui/ErrorCard';
import { EmptyState } from '../components/ui/EmptyState';
import { Skeleton } from '../components/ui/Skeleton';
import { Badge } from '../components/ui/badge';
import { PageHeader } from '../components/ui/PageHeader';
import { Select } from '../components/ui/fields';

/**
 * Notification delivery history.
 *
 * Shows the provider's real outcome per attempt: a row exists only because a
 * send was attempted, and `status` / `error_message` are what the provider
 * returned. A failed delivery is as visible as a successful one.
 */
export default function NotificationLogPage() {
  const [status, setStatus] = useState('');
  const [eventType, setEventType] = useState('');

  const { data: logs = [], isLoading, isError, refetch } = useQuery({
    queryKey: ['notification-logs', { status, eventType }],
    queryFn: () =>
      notificationApi.listLogs({
        status: status || undefined,
        event_type: eventType || undefined,
        limit: 200,
      }),
  });

  const failed = logs.filter((l) => l.status === 'FAILED').length;

  return (
    <div className="space-y-4">
      <PageHeader
        title="Notification history"
        subtitle={
          logs.length === 0
            ? 'Every attempted delivery, with the provider response'
            : `${logs.length} recent deliveries · ${failed} failed`
        }
      />

      <div className="flex flex-wrap items-center gap-3">
        <Select
          aria-label="Filter by status"
          className="w-auto"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
        >
          <option value="">All statuses</option>
          <option value="SENT">Sent</option>
          <option value="FAILED">Failed</option>
          <option value="PENDING">Pending</option>
        </Select>
        <Select
          aria-label="Filter by event"
          className="w-auto"
          value={eventType}
          onChange={(e) => setEventType(e.target.value)}
        >
          <option value="">All events</option>
          <option value="alarm">Alarm</option>
          <option value="dispense_code">Dispense code</option>
          <option value="test">Test</option>
        </Select>
      </div>

      {isError ? <ErrorCard message="Could not load delivery history." onRetry={() => refetch()} /> : null}

      {isLoading ? (
        <div className="space-y-2">
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
        </div>
      ) : logs.length === 0 ? (
        <EmptyState
          title="No deliveries yet"
          hint="Notifications are logged here with the provider's own response."
        />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <caption className="sr-only">Notification delivery history</caption>
            <thead>
              <tr className="border-b border-line text-left text-secondary">
                <th scope="col" className="px-3 py-2">When</th>
                <th scope="col" className="px-3 py-2">Event</th>
                <th scope="col" className="px-3 py-2">Channel</th>
                <th scope="col" className="px-3 py-2">Recipient</th>
                <th scope="col" className="px-3 py-2">Status</th>
                <th scope="col" className="px-3 py-2">Provider</th>
              </tr>
            </thead>
            <tbody>
              {logs.map((log) => (
                <tr key={log.id} className="border-b border-line/60 align-top hover:bg-inset">
                  <td className="whitespace-nowrap px-3 py-2 text-secondary">
                    {new Date(log.created_at).toLocaleString()}
                  </td>
                  <td className="px-3 py-2">
                    <Badge variant="info">{log.event_type}</Badge>
                    {log.event_ref ? (
                      <span className="block font-mono text-xs text-muted">{log.event_ref}</span>
                    ) : null}
                  </td>
                  <td className="px-3 py-2 text-secondary">{log.channel}</td>
                  <td className="px-3 py-2 font-mono text-xs">{log.recipient}</td>
                  <td className="px-3 py-2">
                    <Badge variant={log.status === 'SENT' ? 'success' : log.status === 'FAILED' ? 'danger' : 'warning'}>
                      {log.status}
                    </Badge>
                    {log.retry_count > 0 ? (
                      <span className="block text-xs text-muted">{log.retry_count} retries</span>
                    ) : null}
                  </td>
                  <td className="px-3 py-2 text-xs text-muted">
                    {log.provider_message_id ?? '—'}
                    {log.error_message ? (
                      <span className="block text-rose-600">{log.error_message}</span>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}