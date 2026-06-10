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

      <section className="rounded-3xl border border-cyan-500/20 bg-[radial-gradient(circle_at_top_left,_rgba(6,182,212,0.14),_transparent_28%),radial-gradient(circle_at_top_right,_rgba(16,185,129,0.14),_transparent_24%),linear-gradient(145deg,rgba(15,23,42,0.96),rgba(2,6,23,0.96))] p-6 md:p-8">

        <div className="max-w-3xl space-y-4">

          <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-cyan-300">

            <BookOpenText className="h-3.5 w-3.5" />

            {t('aboutPage.productFramingBadge')}

          </div>

          <h2 className="text-2xl font-bold text-white md:text-3xl">

            {t('aboutPage.heroTitle')}

          </h2>

          <p className="text-sm leading-6 text-slate-300 md:text-base">

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



      <section className="rounded-2xl border border-red-500/20 bg-red-500/5 p-5">

        <div className="flex items-center gap-3">

          <Library className="h-5 w-5 text-red-300" />

          <h3 className="text-lg font-semibold text-white">{t('aboutPage.paperSectionTitle')}</h3>

        </div>

        <p className="mt-3 text-sm leading-6 text-slate-300">

          <strong className="text-white">{t('aboutPage.paperBoldTitle')}</strong>

          {' '}{t('aboutPage.paperBody')}

        </p>

        <a

          href="https://doi.org/10.1111/2041-210x.70285"

          target="_blank"

          rel="noopener noreferrer"

          className="mt-4 inline-flex items-center gap-2 text-sm text-cyan-300 hover:text-cyan-200"

        >

          {t('aboutPage.openDoi')}

          <ExternalLink className="h-4 w-4" />

        </a>

      </section>



      <section className="grid gap-4 lg:grid-cols-2">

        <div className="rounded-2xl border border-red-500/20 bg-red-500/5 p-5">

          <div className="mb-4 flex items-center gap-3">

            <Boxes className="h-5 w-5 text-red-300" />

            <h3 className="text-lg font-semibold text-white">{t('aboutPage.painPointsTitle')}</h3>

          </div>

          <div className="space-y-3">

            {painPoints.map((item, index) => (

              <div key={item.title} className="rounded-2xl border border-red-500/10 bg-slate-950/35 p-4">

                <div className="flex gap-3">

                  <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-red-500/15 text-xs font-semibold text-red-300">

                    {index + 1}

                  </span>

                  <div>

                    <p className="text-sm font-semibold text-red-200">{item.title}</p>

                    <p className="mt-2 text-sm leading-6 text-slate-400">{item.detail}</p>

                  </div>

                </div>

              </div>

            ))}

          </div>

        </div>



        <div className="rounded-2xl border border-emerald-500/20 bg-emerald-500/5 p-5">

          <div className="mb-4 flex items-center gap-3">

            <ShieldCheck className="h-5 w-5 text-emerald-300" />

            <h3 className="text-lg font-semibold text-white">{t('aboutPage.productResponsesTitle')}</h3>

          </div>

          <div className="space-y-3">

            {responses.map((item, index) => (

              <div key={`response-${index}`} className="rounded-2xl border border-emerald-500/10 bg-slate-950/35 p-4">

                <div className="flex gap-3">

                  <BadgeCheck className="mt-0.5 h-4 w-4 shrink-0 text-emerald-300" />

                  <div>

                    <p className="text-xs uppercase tracking-[0.18em] text-emerald-300/80">{t('aboutPage.responseLabel', { index: index + 1 })}</p>

                    <p className="mt-2 text-sm leading-6 text-slate-300">{item}</p>

                  </div>

                </div>

              </div>

            ))}

          </div>

        </div>

      </section>



      <section className="rounded-2xl border border-white/10 bg-white/5 p-5">

        <div className="flex items-center gap-3">

          <Workflow className="h-5 w-5 text-cyan-300" />

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



      <section className="rounded-2xl border border-white/10 bg-white/5 p-5">

        <div className="flex items-center gap-3">

          <ArrowRight className="h-5 w-5 text-violet-300" />

          <h3 className="text-lg font-semibold text-white">{t('aboutPage.designRuleTitle')}</h3>

        </div>

        <p className="mt-3 text-sm leading-7 text-slate-300">

          {t('aboutPage.designRuleBody')}

        </p>

      </section>

    </div>

  )

}



function Panel({ icon: Icon, title, tone, items }) {

  const toneClass = tone === 'violet'

    ? 'border-violet-500/20 bg-violet-500/5 text-violet-300'

    : 'border-emerald-500/20 bg-emerald-500/5 text-emerald-300'



  return (

    <div className="rounded-2xl border border-white/10 bg-white/5 p-5">

      <div className="mb-4 flex items-center gap-3">

        <span className={`rounded-2xl border px-3 py-3 ${toneClass}`}>

          <Icon className="h-5 w-5" />

        </span>

        <h3 className="text-lg font-semibold text-white">{title}</h3>

      </div>

      <div className="space-y-3">

        {items.map((item, idx) => (

          <div key={typeof item === 'string' ? item : idx} className="rounded-2xl border border-white/10 bg-slate-950/35 p-4 text-sm leading-6 text-slate-300">

            {item}

          </div>

        ))}

      </div>

    </div>

  )

}



function FlowCard({ icon: Icon, title, body }) {

  return (

    <div className="rounded-2xl border border-white/10 bg-slate-950/35 p-4">

      <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-2xl border border-cyan-500/20 bg-cyan-500/10 text-cyan-300">

        <Icon className="h-5 w-5" />

      </div>

      <p className="text-sm font-semibold text-white">{title}</p>

      <p className="mt-2 text-sm leading-6 text-slate-400">{body}</p>

    </div>

  )

}


