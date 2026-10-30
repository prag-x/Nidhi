import { Link } from 'react-router-dom'
import { EmptyState } from '@/components/ui'
import { t } from '@/lib/i18n'

export default function NotFound() {
  return (
    <EmptyState title={t('Page not found')}>
      <Link to="/" className="font-medium text-brand-700 hover:underline">{t('Back to the dashboard')}</Link>
    </EmptyState>
  )
}
