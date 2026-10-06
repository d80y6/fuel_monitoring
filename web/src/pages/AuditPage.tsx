import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { auditApi } from '../api/admin';
import { ErrorCard } from '../components/ui/ErrorCard';
import { EmptyState } from '../components/ui/EmptyState';
import { Skeleton } from '../components/ui/Skeleton';
import { Badge } from '../components/ui/badge';
import { PageHeader } from '../components/ui/PageHeader';
import { Select } from '../components/ui/fields';
import { isPlatformAdmin } from '../lib/roles';
import { useAuthStore } from '../store/auth';

/**
 * Audit trail.
 *
 * Read-only by construction: the server exposes no mutation route for audit
 * events. Filters cover who / what / which entity, and a platform admin can
 * narrow to one organization.
 */
export default function AuditPage() {
  const user = useAuthStore((s) => s.user);
  const platform = isPlatformAdmin(user);

  const [action, setAction] = useState('');
  const [entityType, setEntityType] = useState('');
  const [limit, setLimit] = useState(100);

  const { data: events = [], isLoading, isError, refetch } = useQuery({
    queryKey: ['audit-events', { action, entityType, limit }],
    queryFn: () =>
      auditApi.list({
        action: action || undefined,
        entity_type: entityType || undefined,
        limit,
      }),
  });

  const entityTypes = [...new Set(events.map((e) => e.entity_type))].sort();

  return (
    <div className="space-y-4">
      <PageHeader
        title="Audit log"
        subtitle="Append-only record of configuration and access changes"
      />

      <div className="flex flex-wrap items-center gap-3">
        <Select
          aria-label="Filter by action"
          className="w-auto"
          value={action}
          onChange={(e) => setAction(e.target.value)}
        >
          <option value="">All actions</option>
          {[
            'alarm.ack',
            'alarm.resolve',
            'company.create',
            'company.update',
            'company.delete',
            'notification_gateway.create',
            'notification_gateway.update',
            'notification_gateway.delete',
            'notification_gateway.test',
            'notification_rule.create',
            'notification_rule.update',
            'notification_rule.delete',
            'site.create',
            'site.update',
            'site.delete',
            'tank.create',
            'tank.update',
            'tank.delete',
            'user.create',
            'user.update',
            'user.deactivate',
            'user.restore',
            'user.set_password',
          ]
            .filter((a) => events.some((e) => e.action === a) || a === action)
            .map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
        </Select>
        <Select
          aria-label="Filter by entity type"
          className="w-auto"
          value={entityType}
          onChange={(e) => setEntityType(e.target.value)}
        >
          <option value="">All entities</option>
          {entityTypes.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </Select>
        <Select
          aria-label="Rows"
          className="w-auto"
          value={String(limit)}
          onChange={(e) => setLimit(Number(e.target.value))}
        >
          {[50, 100, 250, 500].map((n) => (
            <option key={n} value={n}>
              {n} rows
            </option>
          ))}
        </Select>
      </div>

      {isError ? <ErrorCard message="Could not load the audit log." onRetry={() => refetch()} /> : null}

      {isLoading ? (
        <div className="space-y-2">
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
        </div>
      ) : events.length === 0 ? (
        <EmptyState
          title="No audit events"
          hint={
            platform
              ? 'Changes made through the API appear here.'
              : 'Configuration changes made by your organization appear here.'
          }
        />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <caption className="sr-only">Audit events, newest first</caption>
            <thead>
              <tr className="border-b border-line text-left text-secondary">
                <th scope="col" className="px-3 py-2">When</th>
                <th scope="col" className="px-3 py-2">Actor</th>
                <th scope="col" className="px-3 py-2">Action</th>
                <th scope="col" className="px-3 py-2">Entity</th>
                <th scope="col" className="px-3 py-2">Detail</th>
              </tr>
            </thead>
            <tbody>
              {events.map((event) => (
                <tr key={event.id} className="border-b border-line/60 align-top hover:bg-inset">
                  <td className="whitespace-nowrap px-3 py-2 text-secondary">
                    {new Date(event.at).toLocaleString()}
                  </td>
                  <td className="px-3 py-2">{event.actor_username ?? 'system'}</td>
                  <td className="px-3 py-2">
                    <Badge variant={event.action.includes('delete') ? 'danger' : event.action.includes('create') ? 'success' : 'default'}>
                      {event.action}
                    </Badge>
                  </td>
                  <td className="px-3 py-2 text-secondary">
                    {event.entity_type}
                    {event.entity_id ? (
                      <span className="block font-mono text-xs text-muted">{event.entity_id}</span>
                    ) : null}
                  </td>
                  <td className="px-3 py-2 font-mono text-xs text-muted">
                    {event.detail ? JSON.stringify(event.detail) : '—'}
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