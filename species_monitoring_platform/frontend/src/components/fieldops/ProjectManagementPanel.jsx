import React, { useCallback, useEffect, useRef, useState } from 'react'
import {
  ChevronDown,
  ChevronRight,
  FolderOpen,
  Loader2,
  MapPin,
  Plus,
  Route,
  Save,
  Trash2,
  Upload,
} from 'lucide-react'
import {
  createFieldSurveySite,
  createSurveyProject,
  createSurveyRoute,
  deleteFieldSurveySite,
  deleteSurveyProject,
  deleteSurveyRoute,
  getFieldSurveySites,
  getSurveyProjects,
  getSurveyRoutes,
  getApiErrorMessage,
  importSurveyRoute,
} from '../../lib/api'

/**
 * Hierarchical project/site/route management panel.
 * Allows pre-creating survey structure before going to the field.
 */
export default function ProjectManagementPanel({ locale = 'zh', isOnline, onDataChanged }) {
  const isZh = locale === 'zh'
  const [expanded, setExpanded] = useState(true)
  const [projects, setProjects] = useState([])
  const [sites, setSites] = useState({})
  const [routes, setRoutes] = useState({})
  const [expandedProjects, setExpandedProjects] = useState({})
  const [expandedSites, setExpandedSites] = useState({})
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState('')

  // Forms
  const [showProjectForm, setShowProjectForm] = useState(false)
  const [projectForm, setProjectForm] = useState({ name: '', region: '' })
  const [siteFormFor, setSiteFormFor] = useState('')
  const [siteForm, setSiteForm] = useState({ name: '', habitat_type: '', latitude: '', longitude: '' })
  const [routeFormFor, setRouteFormFor] = useState('')
  const [routeForm, setRouteForm] = useState({ name: '', route_type: 'transect' })
  const [confirmDelete, setConfirmDelete] = useState(null)
  const [confirmDeleteInput, setConfirmDeleteInput] = useState('')
  const [importForSite, setImportForSite] = useState(null)
  const [dragOver, setDragOver] = useState('')
  const [importResult, setImportResult] = useState(null)
  const fileInputRef = useRef(null)

  const refreshProjects = useCallback(async () => {
    if (!isOnline) return
    setLoading(true)
    setError(null)
    try {
      const data = await getSurveyProjects()
      setProjects(data.projects || [])
    } catch (err) {
      setError(getApiErrorMessage(err, isZh ? '加载项目失败' : 'Failed to load projects'))
    } finally {
      setLoading(false)
    }
  }, [isOnline, isZh])

  const loadSitesForProject = useCallback(async (projectId) => {
    if (!isOnline || !projectId) return
    try {
      const data = await getFieldSurveySites(projectId)
      setSites((prev) => ({ ...prev, [projectId]: data.sites || [] }))
    } catch (err) {
      setError(getApiErrorMessage(err, isZh ? '加载站点失败' : 'Failed to load sites'))
    }
  }, [isOnline, isZh])

  const loadRoutesForSite = useCallback(async (projectId, siteId) => {
    if (!isOnline || !siteId) return
    try {
      const data = await getSurveyRoutes(projectId, siteId)
      setRoutes((prev) => ({ ...prev, [siteId]: data.routes || [] }))
    } catch (err) {
      setError(getApiErrorMessage(err, isZh ? '加载路线失败' : 'Failed to load routes'))
    }
  }, [isOnline, isZh])

  useEffect(() => {
    if (expanded && isOnline) refreshProjects()
  }, [expanded, isOnline, refreshProjects])

  function toggleProject(projectId) {
    const next = !expandedProjects[projectId]
    setExpandedProjects((prev) => ({ ...prev, [projectId]: next }))
    if (next && !sites[projectId]) loadSitesForProject(projectId)
  }

  function toggleSite(projectId, siteId) {
    const next = !expandedSites[siteId]
    setExpandedSites((prev) => ({ ...prev, [siteId]: next }))
    if (next && !routes[siteId]) loadRoutesForSite(projectId, siteId)
  }

  async function handleCreateProject() {
    if (!projectForm.name.trim() || !isOnline) return
    setBusy('create-project')
    setError(null)
    try {
      await createSurveyProject({ name: projectForm.name.trim(), region: projectForm.region.trim() })
      setProjectForm({ name: '', region: '' })
      setShowProjectForm(false)
      await refreshProjects()
      onDataChanged?.()
    } catch (err) {
      setError(getApiErrorMessage(err, isZh ? '创建项目失败' : 'Failed to create project'))
    } finally {
      setBusy('')
    }
  }

  async function handleCreateSite(projectId) {
    if (!siteForm.name.trim() || !isOnline) return
    setBusy(`create-site-${projectId}`)
    setError(null)
    try {
      await createFieldSurveySite({
        project_id: projectId,
        name: siteForm.name.trim(),
        habitat_type: siteForm.habitat_type.trim(),
        latitude: siteForm.latitude ? parseFloat(siteForm.latitude) : null,
        longitude: siteForm.longitude ? parseFloat(siteForm.longitude) : null,
      })
      setSiteForm({ name: '', habitat_type: '', latitude: '', longitude: '' })
      setSiteFormFor('')
      await loadSitesForProject(projectId)
      onDataChanged?.()
    } catch (err) {
      setError(getApiErrorMessage(err, isZh ? '创建站点失败' : 'Failed to create site'))
    } finally {
      setBusy('')
    }
  }

  async function handleCreateRoute(projectId, siteId) {
    if (!routeForm.name.trim() || !isOnline) return
    setBusy(`create-route-${siteId}`)
    setError(null)
    try {
      await createSurveyRoute({
        project_id: projectId,
        site_id: siteId,
        name: routeForm.name.trim(),
        route_type: routeForm.route_type,
      })
      setRouteForm({ name: '', route_type: 'transect' })
      setRouteFormFor('')
      await loadRoutesForSite(projectId, siteId)
      onDataChanged?.()
    } catch (err) {
      setError(getApiErrorMessage(err, isZh ? '创建路线失败' : 'Failed to create route'))
    } finally {
      setBusy('')
    }
  }

  async function handleDelete(entityType, entityId, parentProjectId, parentSiteId) {
    if (!isOnline) return
    setBusy(`delete-${entityId}`)
    setError(null)
    try {
      if (entityType === 'project') {
        await deleteSurveyProject(entityId)
        await refreshProjects()
      } else if (entityType === 'site') {
        await deleteFieldSurveySite(entityId)
        if (parentProjectId) await loadSitesForProject(parentProjectId)
      } else if (entityType === 'route') {
        await deleteSurveyRoute(entityId)
        if (parentSiteId) await loadRoutesForSite(parentProjectId, parentSiteId)
      }
      setConfirmDelete(null)
      setConfirmDeleteInput('')
      onDataChanged?.()
    } catch (err) {
      setError(getApiErrorMessage(err, isZh ? '删除失败' : 'Delete failed'))
    } finally {
      setBusy('')
    }
  }

  async function handleImportFile(file, projectId, siteId) {
    if (!file || !isOnline) return
    const ext = (file.name || '').split('.').pop().toLowerCase()
    if (!['gpx', 'geojson', 'json'].includes(ext)) {
      setError(isZh ? '仅支持 .gpx 和 .geojson 文件格式' : 'Only .gpx and .geojson files are supported')
      return
    }
    setBusy(`import-${siteId}`)
    setError(null)
    setImportResult(null)
    try {
      const data = await importSurveyRoute(file, {
        projectId,
        siteId,
        name: file.name.replace(/\.(gpx|geojson|json)$/i, ''),
        routeType: 'transect',
      })
      const route = data.route || {}
      setImportResult({
        siteId,
        name: route.name || file.name,
        lengthM: Math.round(route.length_m || 0),
        format: route.imported_format || ext,
      })
      await loadRoutesForSite(projectId, siteId)
      onDataChanged?.()
    } catch (err) {
      setError(getApiErrorMessage(err, isZh ? '导入路线失败' : 'Failed to import route'))
    } finally {
      setBusy('')
      setImportForSite(null)
    }
  }

  function handleDrop(e, projectId, siteId) {
    e.preventDefault()
    setDragOver('')
    const file = e.dataTransfer?.files?.[0]
    if (file) handleImportFile(file, projectId, siteId)
  }

  function handleFileInputChange(e, projectId, siteId) {
    const file = e.target?.files?.[0]
    if (file) handleImportFile(file, projectId, siteId)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const ROUTE_TYPE_OPTIONS = [
    { id: 'transect', label: isZh ? '样线' : 'Transect' },
    { id: 'point_count', label: isZh ? '样点' : 'Point count' },
    { id: 'station', label: isZh ? '固定站' : 'Station' },
    { id: 'plot', label: isZh ? '样方' : 'Plot' },
  ]

  return (
    <div className="rounded-2xl border border-white/[0.06] bg-white/[0.03]">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center justify-between px-4 py-3"
      >
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#0A84FF]/15">
            <FolderOpen className="h-4 w-4 text-[#0A84FF]" />
          </div>
          <h3 className="text-[15px] font-semibold text-white">
            {isZh ? '项目管理' : 'Project Management'}
          </h3>
          <span className="rounded-full bg-white/[0.06] px-2.5 py-0.5 text-[12px] font-medium text-white/40">
            {projects.length}
          </span>
        </div>
        {expanded ? <ChevronDown className="h-4 w-4 text-white/30" /> : <ChevronRight className="h-4 w-4 text-white/30" />}
      </button>

      {expanded && (
        <div className="space-y-3 px-4 pb-4">
          <p className="text-[12px] text-white/30">
            {isZh ? '在野外调查前预先创建项目、站点和路线结构。' : 'Pre-create project, site, and route structure before field work.'}
          </p>

          {error && (
            <div className="rounded-[12px] bg-[#FF453A]/10 px-4 py-2.5 text-[13px] text-[#FF453A]">
              {error}
            </div>
          )}

          {!isOnline && (
            <div className="rounded-[12px] bg-[#FF9F0A]/10 px-4 py-2.5 text-[13px] text-[#FF9F0A]">
              {isZh ? '项目管理需要网络连接。' : 'Project management requires network.'}
            </div>
          )}

          {loading && (
            <div className="flex items-center gap-2 text-[13px] text-[#0A84FF]">
              <Loader2 className="h-4 w-4 animate-spin" />
              {isZh ? '加载中...' : 'Loading...'}
            </div>
          )}

          {/* Project list */}
          <div className="rounded-2xl border border-white/[0.06]">
            {projects.map((project, pIdx) => (
              <div key={project.project_id} className={pIdx < projects.length - 1 ? 'border-b border-white/[0.04]' : ''}>
                {/* Project header */}
                <div className="flex items-center gap-3 px-4 py-[12px]">
                  <button onClick={() => toggleProject(project.project_id)} className="flex items-center gap-2 text-white">
                    {expandedProjects[project.project_id]
                      ? <ChevronDown className="h-4 w-4 text-white/20" />
                      : <ChevronRight className="h-4 w-4 text-white/20" />}
                    <FolderOpen className="h-4 w-4 text-[#0A84FF]" />
                    <span className="text-[14px] font-medium">{project.name}</span>
                  </button>
                  <span className="ml-auto text-[12px] text-white/25">{project.region || ''}</span>
                  <button
                    onClick={() => setConfirmDelete({ type: 'project', id: project.project_id, name: project.name })}
                    className="rounded-md p-1.5 text-white/15 active:bg-[#FF453A]/10 active:text-[#FF453A]"
                    title={isZh ? '删除项目' : 'Delete project'}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>

                {/* Expanded project: sites */}
                {expandedProjects[project.project_id] && (
                  <div className="ml-8 border-t border-white/[0.04] py-2 pr-4">
                    <div className="space-y-1">
                      {(sites[project.project_id] || []).map((site) => (
                        <div key={site.site_id} className="rounded-[12px] border border-white/[0.06] bg-white/[0.02]">
                          {/* Site header */}
                          <div className="flex items-center gap-2 px-3 py-[10px]">
                            <button onClick={() => toggleSite(project.project_id, site.site_id)} className="flex items-center gap-2 text-white">
                              {expandedSites[site.site_id]
                                ? <ChevronDown className="h-3.5 w-3.5 text-white/20" />
                                : <ChevronRight className="h-3.5 w-3.5 text-white/20" />}
                              <MapPin className="h-3.5 w-3.5 text-[#30D158]" />
                              <span className="text-[13px] font-medium">{site.name}</span>
                            </button>
                            <span className="ml-auto text-[11px] text-white/20">
                              {site.latitude && site.longitude ? `${Number(site.latitude).toFixed(4)}, ${Number(site.longitude).toFixed(4)}` : ''}
                            </span>
                            <button
                              onClick={() => setConfirmDelete({ type: 'site', id: site.site_id, name: site.name, projectId: project.project_id })}
                              className="rounded-md p-1 text-white/15 active:bg-[#FF453A]/10 active:text-[#FF453A]"
                            >
                              <Trash2 className="h-3 w-3" />
                            </button>
                          </div>

                          {/* Expanded site: routes */}
                          {expandedSites[site.site_id] && (
                            <div className="border-t border-white/[0.04] px-3 py-2 pl-8">
                              <div className="space-y-1">
                                {(routes[site.site_id] || []).map((route) => (
                                  <div key={route.route_id} className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-[12px]">
                                    <Route className="h-3.5 w-3.5 text-[#FF9F0A]" />
                                    <span className="font-medium text-white">{route.name}</span>
                                    <span className="text-[11px] text-white/20">{route.route_type}</span>
                                    {route.length_m > 0 && <span className="text-[11px] text-white/20">{Math.round(route.length_m)} m</span>}
                                    <button
                                      onClick={() => setConfirmDelete({ type: 'route', id: route.route_id, name: route.name, projectId: project.project_id, siteId: site.site_id })}
                                      className="ml-auto rounded-md p-1 text-white/15 active:bg-[#FF453A]/10 active:text-[#FF453A]"
                                    >
                                      <Trash2 className="h-2.5 w-2.5" />
                                    </button>
                                  </div>
                                ))}
                                {(routes[site.site_id] || []).length === 0 && (
                                  <p className="text-[11px] text-white/20">{isZh ? '暂无路线' : 'No routes yet'}</p>
                                )}
                              </div>

                              {/* Import route */}
                              {importForSite?.siteId === site.site_id && (
                                <div
                                  className={`mt-2 rounded-[12px] border-2 border-dashed p-4 text-center transition-colors ${
                                    dragOver === site.site_id
                                      ? 'border-[#FF9F0A] bg-[#FF9F0A]/10'
                                      : 'border-white/[0.06] bg-white/[0.02]'
                                  }`}
                                  onDragOver={(e) => { e.preventDefault(); setDragOver(site.site_id) }}
                                  onDragLeave={() => setDragOver('')}
                                  onDrop={(e) => handleDrop(e, project.project_id, site.site_id)}
                                >
                                  {busy === `import-${site.site_id}` ? (
                                    <div className="flex items-center justify-center gap-2 text-[12px] text-[#FF9F0A]">
                                      <Loader2 className="h-4 w-4 animate-spin" />
                                      {isZh ? '正在导入...' : 'Importing...'}
                                    </div>
                                  ) : (
                                    <>
                                      <Upload className="mx-auto h-6 w-6 text-white/20" />
                                      <p className="mt-1 text-[11px] text-white/30">
                                        {isZh ? '拖拽 GPX 或 GeoJSON 文件到此处' : 'Drop GPX or GeoJSON file here'}
                                      </p>
                                      <input
                                        ref={fileInputRef}
                                        type="file"
                                        accept=".gpx,.geojson,.json"
                                        className="hidden"
                                        onChange={(e) => handleFileInputChange(e, project.project_id, site.site_id)}
                                      />
                                      <button
                                        onClick={() => fileInputRef.current?.click()}
                                        className="mt-1.5 rounded-md bg-[#FF9F0A]/15 px-2.5 py-1 text-[11px] text-[#FF9F0A] active:bg-[#FF9F0A]/25"
                                      >
                                        {isZh ? '或点击选择文件' : 'or click to browse'}
                                      </button>
                                      <button
                                        onClick={() => setImportForSite(null)}
                                        className="ml-2 rounded-md px-2.5 py-1 text-[11px] text-white/30 active:text-white"
                                      >
                                        {isZh ? '取消' : 'Cancel'}
                                      </button>
                                    </>
                                  )}
                                </div>
                              )}

                              {importResult?.siteId === site.site_id && (
                                <div className="mt-2 rounded-[12px] bg-[#30D158]/10 px-3 py-2 text-[11px] text-[#30D158]">
                                  ✓ {isZh
                                    ? `已导入 "${importResult.name}" (${importResult.format}, ${importResult.lengthM} m)`
                                    : `Imported "${importResult.name}" (${importResult.format}, ${importResult.lengthM} m)`}
                                </div>
                              )}

                              {/* Add route form */}
                              {routeFormFor === site.site_id ? (
                                <div className="mt-2 space-y-1.5">
                                  <input
                                    value={routeForm.name}
                                    onChange={(e) => setRouteForm((f) => ({ ...f, name: e.target.value }))}
                                    placeholder={isZh ? '路线名称' : 'Route name'}
                                    className="w-full rounded-[10px] border border-white/[0.06] bg-white/[0.04] px-3 py-[8px] text-[13px] text-white placeholder:text-white/20"
                                  />
                                  <select
                                    value={routeForm.route_type}
                                    onChange={(e) => setRouteForm((f) => ({ ...f, route_type: e.target.value }))}
                                    className="w-full rounded-[10px] border border-white/[0.06] bg-white/[0.04] px-3 py-[8px] text-[13px] text-white"
                                  >
                                    {ROUTE_TYPE_OPTIONS.map((opt) => (
                                      <option key={opt.id} value={opt.id}>{opt.label}</option>
                                    ))}
                                  </select>
                                  <div className="flex gap-1.5">
                                    <button
                                      onClick={() => handleCreateRoute(project.project_id, site.site_id)}
                                      disabled={!routeForm.name.trim() || busy.startsWith('create-route')}
                                      className="inline-flex items-center gap-1 rounded-md bg-[#FF9F0A] px-2.5 py-1 text-[11px] font-medium text-white disabled:opacity-40"
                                    >
                                      {busy === `create-route-${site.site_id}` ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />}
                                      {isZh ? '保存' : 'Save'}
                                    </button>
                                    <button onClick={() => setRouteFormFor('')} className="rounded-md px-2.5 py-1 text-[11px] text-white/30 active:text-white">
                                      {isZh ? '取消' : 'Cancel'}
                                    </button>
                                  </div>
                                </div>
                              ) : (
                                <div className="mt-1.5 flex items-center gap-2">
                                  <button
                                    onClick={() => { setRouteFormFor(site.site_id); setRouteForm({ name: '', route_type: 'transect' }) }}
                                    className="inline-flex items-center gap-1 text-[11px] text-[#FF9F0A] active:text-[#FF9F0A]/70"
                                  >
                                    <Plus className="h-3 w-3" /> {isZh ? '添加路线' : 'Add route'}
                                  </button>
                                  <button
                                    onClick={() => { setImportForSite({ siteId: site.site_id, projectId: project.project_id }); setImportResult(null) }}
                                    className="inline-flex items-center gap-1 text-[11px] text-[#FF9F0A] active:text-[#FF9F0A]/70"
                                  >
                                    <Upload className="h-3 w-3" /> {isZh ? '导入路线' : 'Import route'}
                                  </button>
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      ))}
                      {(sites[project.project_id] || []).length === 0 && (
                        <p className="text-[11px] text-white/20">{isZh ? '暂无站点' : 'No sites yet'}</p>
                      )}
                    </div>

                    {/* Add site form */}
                    {siteFormFor === project.project_id ? (
                      <div className="mt-2 space-y-1.5">
                        <input
                          value={siteForm.name}
                          onChange={(e) => setSiteForm((f) => ({ ...f, name: e.target.value }))}
                          placeholder={isZh ? '站点名称' : 'Site name'}
                          className="w-full rounded-[10px] border border-white/[0.06] bg-white/[0.04] px-3 py-[8px] text-[13px] text-white placeholder:text-white/20"
                        />
                        <input
                          value={siteForm.habitat_type}
                          onChange={(e) => setSiteForm((f) => ({ ...f, habitat_type: e.target.value }))}
                          placeholder={isZh ? '栖息地类型（可选）' : 'Habitat type (optional)'}
                          className="w-full rounded-[10px] border border-white/[0.06] bg-white/[0.04] px-3 py-[8px] text-[13px] text-white placeholder:text-white/20"
                        />
                        <div className="grid grid-cols-2 gap-1.5">
                          <input
                            value={siteForm.latitude}
                            onChange={(e) => setSiteForm((f) => ({ ...f, latitude: e.target.value }))}
                            placeholder={isZh ? '纬度' : 'Latitude'}
                            className="rounded-[10px] border border-white/[0.06] bg-white/[0.04] px-3 py-[8px] text-[13px] text-white placeholder:text-white/20"
                          />
                          <input
                            value={siteForm.longitude}
                            onChange={(e) => setSiteForm((f) => ({ ...f, longitude: e.target.value }))}
                            placeholder={isZh ? '经度' : 'Longitude'}
                            className="rounded-[10px] border border-white/[0.06] bg-white/[0.04] px-3 py-[8px] text-[13px] text-white placeholder:text-white/20"
                          />
                        </div>
                        <div className="flex gap-1.5">
                          <button
                            onClick={() => handleCreateSite(project.project_id)}
                            disabled={!siteForm.name.trim() || busy.startsWith('create-site')}
                            className="inline-flex items-center gap-1 rounded-md bg-[#30D158] px-2.5 py-1 text-[11px] font-medium text-white disabled:opacity-40"
                          >
                            {busy === `create-site-${project.project_id}` ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />}
                            {isZh ? '保存' : 'Save'}
                          </button>
                          <button onClick={() => setSiteFormFor('')} className="rounded-md px-2.5 py-1 text-[11px] text-white/30 active:text-white">
                            {isZh ? '取消' : 'Cancel'}
                          </button>
                        </div>
                      </div>
                    ) : (
                      <button
                        onClick={() => { setSiteFormFor(project.project_id); setSiteForm({ name: '', habitat_type: '', latitude: '', longitude: '' }) }}
                        className="mt-1.5 inline-flex items-center gap-1 text-[11px] text-[#30D158] active:text-[#30D158]/70"
                      >
                        <Plus className="h-3 w-3" /> {isZh ? '添加站点' : 'Add site'}
                      </button>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* Add project form */}
          {showProjectForm ? (
            <div className="space-y-2 rounded-2xl border border-white/[0.06] bg-white/[0.02] p-4">
              <p className="text-[13px] font-medium text-[#0A84FF]">{isZh ? '新建项目' : 'New project'}</p>
              <input
                value={projectForm.name}
                onChange={(e) => setProjectForm((f) => ({ ...f, name: e.target.value }))}
                placeholder={isZh ? '项目名称' : 'Project name'}
                className="w-full rounded-[10px] border border-white/[0.06] bg-white/[0.04] px-3 py-[9px] text-[14px] text-white placeholder:text-white/20"
              />
              <input
                value={projectForm.region}
                onChange={(e) => setProjectForm((f) => ({ ...f, region: e.target.value }))}
                placeholder={isZh ? '区域（可选）' : 'Region (optional)'}
                className="w-full rounded-[10px] border border-white/[0.06] bg-white/[0.04] px-3 py-[9px] text-[14px] text-white placeholder:text-white/20"
              />
              <div className="flex gap-2">
                <button
                  onClick={handleCreateProject}
                  disabled={!projectForm.name.trim() || busy === 'create-project'}
                  className="inline-flex items-center gap-1.5 rounded-[10px] bg-[#0A84FF] px-4 py-[9px] text-[14px] font-medium text-white disabled:opacity-40"
                >
                  {busy === 'create-project' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                  {isZh ? '创建项目' : 'Create project'}
                </button>
                <button onClick={() => setShowProjectForm(false)} className="rounded-[10px] px-4 py-[9px] text-[14px] text-white/40 active:text-white">
                  {isZh ? '取消' : 'Cancel'}
                </button>
              </div>
            </div>
          ) : (
            <button
              onClick={() => { setShowProjectForm(true); setProjectForm({ name: '', region: '' }) }}
              disabled={!isOnline}
              className="inline-flex items-center gap-1.5 rounded-[12px] bg-[#0A84FF]/15 px-4 py-[11px] text-[14px] font-medium text-[#0A84FF] active:bg-[#0A84FF]/25 disabled:opacity-40"
            >
              <Plus className="h-4 w-4" /> {isZh ? '新建项目' : 'New project'}
            </button>
          )}

          {/* Delete confirmation — projects require typing the exact name to prevent accidents. */}
          {confirmDelete && (() => {
            const requiresNameMatch = confirmDelete.type === 'project'
            const nameMatched = !requiresNameMatch || confirmDeleteInput.trim() === (confirmDelete.name || '').trim()
            const cascadeText = confirmDelete.type === 'project'
              ? (isZh
                ? '该项目下的所有站点、路线、调查事件、观测和轨迹都会一并删除，且无法恢复。'
                : 'All sites, routes, survey events, observations, and tracks under this project will be deleted and cannot be restored.')
              : confirmDelete.type === 'site'
                ? (isZh ? '该站点下的所有路线和观测都会一并删除。' : 'All routes and observations under this site will be deleted.')
                : (isZh ? '该路线及其轨迹会被删除。' : 'This route and its tracks will be deleted.')
            return (
              <div className="space-y-2 rounded-[12px] bg-[#FF453A]/10 p-4">
                <p className="text-[13px] font-medium text-[#FF453A]">
                  {isZh
                    ? `确认删除${confirmDelete.type === 'project' ? '项目' : confirmDelete.type === 'site' ? '站点' : '路线'} "${confirmDelete.name}"？此操作不可撤销。`
                    : `Delete ${confirmDelete.type} "${confirmDelete.name}"? This cannot be undone.`}
                </p>
                <p className="text-[12px] text-[#FF453A]/70">{cascadeText}</p>
                {requiresNameMatch && (
                  <div className="space-y-1">
                    <p className="text-[11px] text-[#FF453A]/70">
                      {isZh
                        ? `请输入项目名称 "${confirmDelete.name}" 以确认删除：`
                        : `Type the project name "${confirmDelete.name}" to confirm:`}
                    </p>
                    <input
                      value={confirmDeleteInput}
                      onChange={(e) => setConfirmDeleteInput(e.target.value)}
                      placeholder={confirmDelete.name}
                      autoFocus
                      autoComplete="off"
                      autoCorrect="off"
                      spellCheck={false}
                      className="w-full rounded-[8px] border border-[#FF453A]/30 bg-white/[0.04] px-3 py-[7px] text-[13px] text-white placeholder:text-white/15 focus:border-[#FF453A]/60 focus:outline-none"
                    />
                  </div>
                )}
                <div className="flex gap-2">
                  <button
                    onClick={() => handleDelete(confirmDelete.type, confirmDelete.id, confirmDelete.projectId, confirmDelete.siteId)}
                    disabled={busy.startsWith('delete-') || !nameMatched}
                    className="inline-flex items-center gap-1 rounded-md bg-[#FF453A] px-3 py-1.5 text-[12px] font-medium text-white disabled:opacity-40"
                  >
                    {busy === `delete-${confirmDelete.id}` ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
                    {isZh ? '确认删除' : 'Confirm delete'}
                  </button>
                  <button
                    onClick={() => { setConfirmDelete(null); setConfirmDeleteInput('') }}
                    className="rounded-md px-3 py-1.5 text-[12px] text-white/30 active:text-white"
                  >
                    {isZh ? '取消' : 'Cancel'}
                  </button>
                </div>
              </div>
            )
          })()}
        </div>
      )}
    </div>
  )
}
