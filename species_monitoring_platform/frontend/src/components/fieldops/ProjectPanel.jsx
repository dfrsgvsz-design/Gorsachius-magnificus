import React from 'react'
import { ChevronRight, FolderOpen } from 'lucide-react'

/**
 * Project selector — row-list style matching ProjectManagementPanel.
 * Field workers select from pre-created projects (admin creates in SettingsTab).
 */
export default function ProjectPanel({
  copy,
  locale = 'zh',
  projects,
  currentProjectId,
  projectForm,
  onSelectProject,
  onChangeProjectForm,
  onSubmitProject,
}) {
  const isZh = locale === 'zh'
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 px-1">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#0A84FF]/15">
          <FolderOpen className="h-4 w-4 text-[#0A84FF]" />
        </div>
        <h3 className="flex-1 text-[15px] font-semibold text-white">{copy.project}</h3>
        <span className="rounded-full bg-white/[0.06] px-2.5 py-0.5 text-[12px] font-medium text-white/40">
          {projects.length}
        </span>
      </div>
      <div className="rounded-2xl border border-white/[0.06] bg-white/[0.03]">
        {projects.length === 0 && (
          <p className="px-4 py-5 text-center text-[14px] text-white/25">
            {isZh ? '暂无项目，请联系管理员创建' : 'No projects. Ask admin to create.'}
          </p>
        )}
        {projects.map((project, idx) => {
          const isActive = project.project_id === currentProjectId
          return (
            <button
              key={project.project_id}
              onClick={() => onSelectProject(project.project_id)}
              className={`flex w-full items-center gap-3 px-4 py-[13px] text-left transition-colors active:bg-white/[0.04] ${
                idx < projects.length - 1 ? 'border-b border-white/[0.04]' : ''
              }`}
            >
              <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${isActive ? 'bg-[#0A84FF]/15' : 'bg-white/[0.06]'}`}>
                <FolderOpen className={`h-4 w-4 ${isActive ? 'text-[#0A84FF]' : 'text-white/30'}`} />
              </div>
              <div className="min-w-0 flex-1">
                <span className={`block truncate text-[15px] ${isActive ? 'font-medium text-white' : 'text-white/80'}`}>
                  {project.name}
                </span>
                {project.region && <span className="text-[12px] text-white/25">{project.region}</span>}
              </div>
              {isActive && (
                <span className="shrink-0 rounded-full bg-[#0A84FF]/15 px-2.5 py-1 text-[11px] font-medium text-[#0A84FF]">
                  {isZh ? '当前' : 'Active'}
                </span>
              )}
              <ChevronRight className={`h-4 w-4 shrink-0 ${isActive ? 'text-[#0A84FF]' : 'text-white/15'}`} />
            </button>
          )
        })}
      </div>
    </div>
  )
}
