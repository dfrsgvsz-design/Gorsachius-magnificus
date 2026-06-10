import React from 'react'
import { Crosshair, MapPinned, Save } from 'lucide-react'

export default function ProjectManagementPanel({
  copy,
  surveyState,
  currentProjectId,
  currentSiteId,
  projectSites,
  projectForm,
  siteForm,
  onSetProjectForm,
  onSetSiteForm,
  onSelectProject,
  onSelectSite,
  onCreateProject,
  onSaveSite,
  onUseGps,
}) {
  return (
    <>
      <div className="section-shell space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-white">{copy.project}</h3>
          <span className="text-xs text-gray-400">{surveyState.projects.length}</span>
        </div>
        <select
          value={currentProjectId}
          onChange={(event) => onSelectProject(event.target.value)}
          className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white"
        >
          {surveyState.projects.map((project) => (
            <option key={project.project_id} value={project.project_id}>{project.name}</option>
          ))}
        </select>
        <input
          value={projectForm.name}
          onChange={(event) => onSetProjectForm((current) => ({ ...current, name: event.target.value }))}
          placeholder={copy.projectPlaceholder}
          className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white"
        />
        <input
          value={projectForm.region}
          onChange={(event) => onSetProjectForm((current) => ({ ...current, region: event.target.value }))}
          placeholder={copy.regionPlaceholder}
          className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white"
        />
        <button onClick={onCreateProject} className="inline-flex items-center gap-2 rounded-lg bg-cyan-500 px-3 py-2 text-sm font-medium text-white">
          <Save className="h-4 w-4" />
          {copy.createProject}
        </button>
      </div>

      <div className="section-shell space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-white">{copy.site}</h3>
          <span className="text-xs text-gray-400">{projectSites.length}</span>
        </div>
        <select
          value={currentSiteId}
          onChange={(event) => onSelectSite(event.target.value)}
          className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white"
        >
          <option value="">{copy.site}</option>
          {projectSites.map((site) => (
            <option key={site.site_id} value={site.site_id}>{site.name}</option>
          ))}
        </select>
        <input
          value={siteForm.name}
          onChange={(event) => onSetSiteForm((current) => ({ ...current, name: event.target.value }))}
          placeholder={copy.sitePlaceholder}
          className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white"
        />
        <input
          value={siteForm.habitat_type}
          onChange={(event) => onSetSiteForm((current) => ({ ...current, habitat_type: event.target.value }))}
          placeholder={copy.habitatPlaceholder}
          className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white"
        />
        <div className="grid gap-2 sm:grid-cols-[1fr_1fr_auto]">
          <input
            value={siteForm.latitude}
            onChange={(event) => onSetSiteForm((current) => ({ ...current, latitude: event.target.value }))}
            placeholder="Latitude"
            className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white"
          />
          <input
            value={siteForm.longitude}
            onChange={(event) => onSetSiteForm((current) => ({ ...current, longitude: event.target.value }))}
            placeholder="Longitude"
            className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white"
          />
          <button onClick={onUseGps} className="inline-flex items-center justify-center gap-2 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white">
            <Crosshair className="h-4 w-4" />
            {copy.location}
          </button>
        </div>
        <button onClick={onSaveSite} disabled={!currentProjectId} className="inline-flex items-center gap-2 rounded-lg bg-violet-500 px-3 py-2 text-sm font-medium text-white disabled:opacity-50">
          <MapPinned className="h-4 w-4" />
          {copy.saveSite}
        </button>
      </div>
    </>
  )
}
