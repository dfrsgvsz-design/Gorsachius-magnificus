import { useCallback, useEffect, useRef, useState } from 'react'

const OPEN_METEO_URL = 'https://api.open-meteo.com/v1/forecast'

export default function useWeatherCapture({ lat, lon, autoFetch = false }) {
  const [weather, setWeather] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const abortRef = useRef(null)

  const fetchWeather = useCallback(async (latitude, longitude) => {
    const useLat = latitude ?? lat
    const useLon = longitude ?? lon
    if (useLat == null || useLon == null) {
      setError('No coordinates available')
      return null
    }

    setLoading(true)
    setError(null)

    try {
      abortRef.current?.abort()
      const controller = new AbortController()
      abortRef.current = controller

      const params = new URLSearchParams({
        latitude: useLat,
        longitude: useLon,
        current: 'temperature_2m,relative_humidity_2m,wind_speed_10m,wind_direction_10m,weather_code,cloud_cover,precipitation',
        timezone: 'auto',
      })

      const resp = await fetch(`${OPEN_METEO_URL}?${params}`, {
        signal: controller.signal,
        cache: 'no-store',
      })

      if (!resp.ok) throw new Error(`Weather API: ${resp.status}`)

      const data = await resp.json()
      const current = data.current || {}

      const result = {
        temperature: current.temperature_2m,
        humidity: current.relative_humidity_2m,
        wind_speed: current.wind_speed_10m,
        wind_direction: current.wind_direction_10m,
        weather_code: current.weather_code,
        cloud_cover: current.cloud_cover,
        precipitation: current.precipitation,
        timestamp: current.time || new Date().toISOString(),
        source: 'open-meteo',
        coordinates: { lat: useLat, lon: useLon },
        description: describeWeatherCode(current.weather_code),
      }

      setWeather(result)
      return result
    } catch (err) {
      if (err.name !== 'AbortError') {
        setError(err.message)
      }
      return null
    } finally {
      setLoading(false)
    }
  }, [lat, lon])

  useEffect(() => {
    if (autoFetch && lat != null && lon != null) {
      fetchWeather()
    }
  }, [autoFetch, lat, lon, fetchWeather])

  useEffect(() => () => {
    abortRef.current?.abort()
  }, [])

  return { weather, loading, error, fetchWeather }
}

function describeWeatherCode(code) {
  const descriptions = {
    0: 'Clear sky',
    1: 'Mainly clear', 2: 'Partly cloudy', 3: 'Overcast',
    45: 'Foggy', 48: 'Rime fog',
    51: 'Light drizzle', 53: 'Moderate drizzle', 55: 'Dense drizzle',
    61: 'Slight rain', 63: 'Moderate rain', 65: 'Heavy rain',
    71: 'Slight snow', 73: 'Moderate snow', 75: 'Heavy snow',
    80: 'Slight rain showers', 81: 'Moderate rain showers', 82: 'Violent rain showers',
    95: 'Thunderstorm', 96: 'Thunderstorm with hail', 99: 'Thunderstorm with heavy hail',
  }
  return descriptions[code] || `Code ${code}`
}
