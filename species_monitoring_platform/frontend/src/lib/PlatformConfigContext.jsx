import React, { createContext, useContext, useEffect, useState } from 'react'
import { getPlatformConfig } from './api'

const PlatformConfigContext = createContext({})

const DEFAULTS = {
  platform: {
    name: 'Biodiversity Field Survey Platform',
    name_zh: '生物多样性野外调查平台',
    short_name: 'FieldSurvey',
    short_name_zh: '野外调查',
  },
  target_species: { scientific_name: '', common_name: '', common_name_zh: '' },
  study_region: { center_lat: 25, center_lon: 110, default_zoom: 5, country_code: 'CN' },
  map: { tile_url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png' },
  features: {},
  theme: { primary_color: '#10b981' },
  analysis: {},
}

export function PlatformConfigProvider({ children }) {
  const [config, setConfig] = useState(DEFAULTS)
  const [configLoaded, setConfigLoaded] = useState(false)

  useEffect(() => {
    getPlatformConfig()
      .then((data) => setConfig({ ...DEFAULTS, ...data }))
      .catch(() => {})
      .finally(() => setConfigLoaded(true))
  }, [])

  const value = { ...config, _loaded: configLoaded }

  return (
    <PlatformConfigContext.Provider value={value}>
      {children}
    </PlatformConfigContext.Provider>
  )
}

export function usePlatformConfig() {
  return useContext(PlatformConfigContext)
}

export default PlatformConfigContext
