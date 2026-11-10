import { AnimatePresence, motion } from 'framer-motion'
import { MessageCircle } from 'lucide-react'
import { useEffect, useState } from 'react'

import { EnrollButton } from '@/features/enrollment/EnrollButton'
import { useSettings } from '@/hooks/queries'
import { useI18n } from '@/i18n'

/** Sticky bottom bar on phones (after scrolling): enroll + WhatsApp in one tap. */
export function MobileCta() {
  const { t } = useI18n()
  const { data } = useSettings()
  const [visible, setVisible] = useState(false)
  useEffect(() => {
    const onScroll = () => setVisible(window.scrollY > 640)
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])
  const whatsapp = data?.contacts.whatsapp
  return (
    <AnimatePresence>
      {visible ? (
        <motion.div initial={{ y: 100 }} animate={{ y: 0 }} exit={{ y: 100 }} className="fixed inset-x-0 bottom-0 z-40 border-t border-line bg-white/95 px-4 pt-3 pb-[calc(0.75rem+env(safe-area-inset-bottom))] backdrop-blur sm:hidden">
          <div className="flex gap-2">
            <EnrollButton className="flex-1" />
            {whatsapp ? (
              <a href={whatsapp} target="_blank" rel="noopener noreferrer" aria-label={t('contacts.whatsapp')} className="grid size-12 shrink-0 place-items-center rounded-full bg-emerald-500 text-white">
                <MessageCircle className="size-5" aria-hidden />
              </a>
            ) : null}
          </div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  )
}
