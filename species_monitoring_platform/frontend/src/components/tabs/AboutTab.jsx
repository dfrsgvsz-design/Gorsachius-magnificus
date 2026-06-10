import React from 'react'

import { useTranslation } from 'react-i18next'

import {

  ArrowRight, AudioLines, BadgeCheck, Bird, BookOpenText, Boxes,

  ExternalLink, Library, Microscope, Radio, ShieldCheck, Workflow,

} from 'lucide-react'



export default function AboutTab() {

  const { t } = useTranslation()

  const birdnetLessons = t('aboutPage.birdnetLessons', { returnObjects: true })

  const platformDifferences = t('aboutPage.platformDifferences', { returnObjects: true })

  const sugaiPainPoints = t('aboutPage.sugaiPainPoints', { returnObjects: true })

  const platformResponses = t('aboutPage.platformResponses', { returnObjects: true })



  const lessons = Array.isArray(birdnetLessons) ? birdnetLessons : []

  const differences = Array.isArray(platformDifferences) ? platformDifferences : []

  const painPoints = Array.isArray(sugaiPainPoints) ? sugaiPainPoints : []

  const responses = Array.isArray(platformResponses) ? platformResponses : []



  return (

    <div className="max-w-5xl space-y-6">

      <section className="glass-card p-6 md:p-8">

        <div className="max-w-3xl space-y-4">

          <div className="inline-flex items-center gap-2 rounded-full border border-white/[0.06] bg-[#0A84FF]/10 px-3 py-1 text-xs text-[#0A84FF]">

            <BookOpenText className="h-3.5 w-3.5" />

            {t('aboutPage.productFramingBadge')}

          </div>

          <h2 className="text-2xl font-bold text-white md:text-3xl">

            {t('aboutPage.heroTitle')}

          </h2>

          <p className="text-sm leading-6 text-white/50 md:text-base">

            {t('aboutPage.heroBody')}

          </p>

        </div>

      </section>



      <section className="grid gap-4 lg:grid-cols-2">

        <Panel

          icon={AudioLines}

          title={t('aboutPage.panelBirdnetTitle')}

          tone="emerald"

          items={lessons}

        />

        <Panel

          icon={Microscope}

          title={t('aboutPage.panelPlatformTitle')}

          tone="violet"

          items={differences}

        />

      </section>



      <section className="rounded-2xl border border-white/[0.06] bg-[#FF453A]/8 p-5">

        <div className="flex items-center gap-3">

          <Library className="h-5 w-5 text-[#FF453A]" />

          <h3 className="text-lg font-semibold text-white">{t('aboutPage.paperSectionTitle')}</h3>

        </div>

        <p className="mt-3 text-sm leading-6 text-white/50">

          <strong className="text-white">{t('aboutPage.paperBoldTitle')}</strong>

          {' '}{t('aboutPage.paperBody')}

        </p>

        <a

          href="https://doi.org/10.1111/2041-210x.70285"

          target="_blank"

          rel="noopener noreferrer"

          className="mt-4 inline-flex items-center gap-2 text-sm text-[#0A84FF] hover:text-[#0A84FF]/80"

        >

          {t('aboutPage.openDoi')}

          <ExternalLink className="h-4 w-4" />

        </a>

      </section>



      <section className="grid gap-4 lg:grid-cols-2">

        <div className="rounded-2xl border border-white/[0.06] bg-[#FF453A]/8 p-5">

          <div className="mb-4 flex items-center gap-3">

            <Boxes className="h-5 w-5 text-[#FF453A]" />

            <h3 className="text-lg font-semibold text-white">{t('aboutPage.painPointsTitle')}</h3>

          </div>

          <div className="space-y-3">

            {painPoints.map((item, index) => (

              <div key={item.title} className="rounded-2xl border border-white/[0.04] bg-white/[0.02] p-4">

                <div className="flex gap-3">

                  <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[#FF453A]/15 text-xs font-semibold text-[#FF453A]">

                    {index + 1}

                  </span>

                  <div>

                    <p className="text-sm font-semibold text-[#FF453A]">{item.title}</p>

                    <p className="mt-2 text-sm leading-6 text-white/40">{item.detail}</p>

                  </div>

                </div>

              </div>

            ))}

          </div>

        </div>



        <div className="rounded-2xl border border-white/[0.06] bg-[#30D158]/8 p-5">

          <div className="mb-4 flex items-center gap-3">

            <ShieldCheck className="h-5 w-5 text-[#30D158]" />

            <h3 className="text-lg font-semibold text-white">{t('aboutPage.productResponsesTitle')}</h3>

          </div>

          <div className="space-y-3">

            {responses.map((item, index) => (

              <div key={`response-${index}`} className="rounded-2xl border border-white/[0.04] bg-white/[0.02] p-4">

                <div className="flex gap-3">

                  <BadgeCheck className="mt-0.5 h-4 w-4 shrink-0 text-[#30D158]" />

                  <div>

                    <p className="text-xs uppercase tracking-[0.18em] text-[#30D158]/80">{t('aboutPage.responseLabel', { index: index + 1 })}</p>

                    <p className="mt-2 text-sm leading-6 text-white/50">{item}</p>

                  </div>

                </div>

              </div>

            ))}

          </div>

        </div>

      </section>



      <section className="rounded-2xl border border-white/[0.06] bg-white/[0.03] p-5">

        <div className="flex items-center gap-3">

          <Workflow className="h-5 w-5 text-[#0A84FF]" />

          <h3 className="text-lg font-semibold text-white">{t('aboutPage.targetShapeTitle')}</h3>

        </div>

        <div className="mt-4 grid gap-3 md:grid-cols-4">

          <FlowCard

            icon={Bird}

            title={t('aboutPage.flowAnalyzeTitle')}

            body={t('aboutPage.flowAnalyzeBody')}

          />

          <FlowCard

            icon={ShieldCheck}

            title={t('aboutPage.flowReviewTitle')}

            body={t('aboutPage.flowReviewBody')}

          />

          <FlowCard

            icon={Radio}

            title={t('aboutPage.flowMonitorTitle')}

            body={t('aboutPage.flowMonitorBody')}

          />

          <FlowCard

            icon={Microscope}

            title={t('aboutPage.flowInterpretTitle')}

            body={t('aboutPage.flowInterpretBody')}

          />

        </div>

      </section>



      <section className="rounded-2xl border border-white/[0.06] bg-white/[0.03] p-5">

        <div className="flex items-center gap-3">

          <ArrowRight className="h-5 w-5 text-[#BF5AF2]" />

          <h3 className="text-lg font-semibold text-white">{t('aboutPage.designRuleTitle')}</h3>

        </div>

        <p className="mt-3 text-sm leading-7 text-white/50">

          {t('aboutPage.designRuleBody')}

        </p>

      </section>

    </div>

  )

}



function Panel({ icon: Icon, title, tone, items }) {

  const toneClass = tone === 'violet'

    ? 'border-white/[0.06] bg-[#BF5AF2]/10 text-[#BF5AF2]'

    : 'border-white/[0.06] bg-[#30D158]/10 text-[#30D158]'



  return (

    <div className="rounded-2xl border border-white/[0.06] bg-white/[0.03] p-5">

      <div className="mb-4 flex items-center gap-3">

        <span className={`rounded-2xl border px-3 py-3 ${toneClass}`}>

          <Icon className="h-5 w-5" />

        </span>

        <h3 className="text-lg font-semibold text-white">{title}</h3>

      </div>

      <div className="space-y-3">

        {items.map((item, idx) => (

          <div key={typeof item === 'string' ? item : idx} className="rounded-2xl border border-white/[0.04] bg-white/[0.02] p-4 text-sm leading-6 text-white/50">

            {item}

          </div>

        ))}

      </div>

    </div>

  )

}



function FlowCard({ icon: Icon, title, body }) {

  return (

    <div className="rounded-2xl border border-white/[0.04] bg-white/[0.02] p-4">

      <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-2xl border border-white/[0.06] bg-[#0A84FF]/10 text-[#0A84FF]">

        <Icon className="h-5 w-5" />

      </div>

      <p className="text-sm font-semibold text-white">{title}</p>

      <p className="mt-2 text-sm leading-6 text-white/40">{body}</p>

    </div>

  )

}


