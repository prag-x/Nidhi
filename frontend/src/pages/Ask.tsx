import AskPanel from '@/components/AskPanel'
import { PageHeader } from '@/components/ui'
import { t } from '@/lib/i18n'

export default function Ask() {
  return (
    <div className="max-w-5xl">
      <PageHeader
        title={t('Ask the portal')}
        subtitle={t('Type a question the way you would ask a colleague. It is turned into the same filters the Deposits page uses, and you can see exactly how it was read.')}
      />
      <AskPanel />
    </div>
  )
}
