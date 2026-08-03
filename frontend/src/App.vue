<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'

interface Artist {
  id: string
  name: string
  images: { url: string }[]
  genres: string[]
  popularity: number
}

interface Track {
  id: string
  name: string
  artists: { name: string }[]
  album: {
    name: string
    images: { url: string }[]
  }
  duration_ms: number
  popularity?: number
}

interface RecentlyPlayedItem {
  track: Track
  played_at: string
}

interface CurrentlyPlaying {
  is_playing: boolean
  item?: Track
  message?: string
}

type TimeRange = 'short_term' | 'medium_term' | 'long_term' | 'recent_week'

const accessToken = ref<string | null>(null)
const refreshToken = ref<string | null>(null)
const topArtists = ref<Artist[]>([])
const topTracks = ref<Track[]>([])
const recentlyPlayed = ref<RecentlyPlayedItem[]>([])
const currentlyPlaying = ref<CurrentlyPlaying | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
const timeRange = ref<TimeRange>('medium_term')

const timeRangeLabels: Record<TimeRange, string> = {
  recent_week: 'Recent (≈1 week)',
  short_term: 'Last 4 Weeks',
  medium_term: 'Last 6 Months',
  long_term: 'All Time'
}

onMounted(async () => {
  const params = new URLSearchParams(window.location.search)
  const token = params.get('access_token')
  const refresh = params.get('refresh_token')

  if (token) {
    accessToken.value = token
    localStorage.setItem('spotify_access_token', token)
    if (refresh) {
      refreshToken.value = refresh
      localStorage.setItem('spotify_refresh_token', refresh)
    }
    window.history.replaceState({}, document.title, '/')
  } else {
    accessToken.value = localStorage.getItem('spotify_access_token')
    refreshToken.value = localStorage.getItem('spotify_refresh_token')
  }

  if (accessToken.value) {
    await fetchAllData()
  }
})

const recentWeekItems = computed(() => {
  const oneWeekAgo = Date.now() - 7 * 24 * 60 * 60 * 1000
  return recentlyPlayed.value.filter(item => {
    return new Date(item.played_at).getTime() >= oneWeekAgo
  })
})

const genreSummary = computed(() => {
  const counts: Record<string, number> = {}
  topArtists.value.forEach(artist => {
    artist.genres.forEach(genre => {
      counts[genre] = (counts[genre] || 0) + 1
    })
  })
  return Object.entries(counts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8)
})

const genreChart = computed(() => {
  const max = Math.max(...genreSummary.value.map(([, count]) => count), 1)
  return genreSummary.value.map(([name, value]) => ({
    name,
    value,
    percent: (value / max) * 100
  }))
})

const artistPopularityChart = computed(() => {
  const items = topArtists.value.slice(0, 8)
  const max = Math.max(...items.map(a => a.popularity || 0), 1)
  return items.map(a => ({
    name: a.name,
    value: a.popularity || 0,
    percent: ((a.popularity || 0) / max) * 100
  }))
})

const trackPopularityChart = computed(() => {
  const items = topTracks.value.slice(0, 8)
  const max = Math.max(...items.map(t => t.popularity || 0), 1)
  return items.map(t => ({
    name: t.name,
    value: t.popularity || 0,
    percent: ((t.popularity || 0) / max) * 100
  }))
})

const recentFrequencyChart = computed(() => {
  const source = timeRange.value === 'recent_week' ? recentWeekItems.value : recentlyPlayed.value
  const counts: Record<string, { name: string; count: number }> = {}

  source.forEach(item => {
    const id = item.track.id
    if (!counts[id]) {
      counts[id] = { name: item.track.name, count: 0 }
    }
    counts[id].count += 1
  })

  const items = Object.values(counts)
    .sort((a, b) => b.count - a.count)
    .slice(0, 8)

  const max = Math.max(...items.map(i => i.count), 1)

  return items.map(i => ({
    name: i.name,
    value: i.count,
    percent: (i.count / max) * 100
  }))
})

const mainstreamScore = computed(() => {
  const artistScores = topArtists.value.map(a => a.popularity || 0)
  const trackScores = topTracks.value.map(t => t.popularity || 0)

  const artistAvg = artistScores.length
    ? artistScores.reduce((a, b) => a + b, 0) / artistScores.length
    : 0

  const trackAvg = trackScores.length
    ? trackScores.reduce((a, b) => a + b, 0) / trackScores.length
    : 0

  const overall = (artistAvg + trackAvg) / 2

  let label = 'Balanced'
  let comparison = 'Your taste sits near the middle of global popularity.'

  if (overall >= 80) {
    label = 'Very Mainstream'
    comparison = 'Your taste is more mainstream than most listeners.'
  } else if (overall >= 65) {
    label = 'Mostly Mainstream'
    comparison = 'Your taste leans mainstream compared with global popularity.'
  } else if (overall >= 45) {
    label = 'Balanced'
    comparison = 'Your taste sits near the middle of global popularity.'
  } else if (overall >= 25) {
    label = 'More Niche'
    comparison = 'Your taste is more niche than global popularity.'
  } else {
    label = 'Deep Cuts'
    comparison = 'Your taste is much more niche than global popularity.'
  }

  return {
    artistAvg: Math.round(artistAvg),
    trackAvg: Math.round(trackAvg),
    overall: Math.round(overall),
    label,
    comparison
  }
})

async function refreshAccessToken(): Promise<boolean> {
  if (!refreshToken.value) return false
  try {
    const response = await fetch(
      `http://127.0.0.1:8000/api/refresh?refresh_token=${refreshToken.value}`
    )
    if (!response.ok) return false
    const data = await response.json()
    if (data.access_token) {
      accessToken.value = data.access_token
      localStorage.setItem('spotify_access_token', data.access_token)
      return true
    }
  } catch (err) {
    console.error('Token refresh failed', err)
  }
  return false
}

async function fetchAllData() {
  if (!accessToken.value) return
  loading.value = true
  error.value = null

  try {
    let token = accessToken.value

    const doFetch = async (url: string) => {
      let res = await fetch(url)
      if (res.status === 401) {
        const refreshed = await refreshAccessToken()
        if (!refreshed || !accessToken.value) throw new Error('Session expired')
        token = accessToken.value
        res = await fetch(url.replace(/access_token=[^&]+/, `access_token=${token}`))
      }
      return res
    }

    // For recent_week we still fetch medium_term tops + recently played
    const rangeForApi = timeRange.value === 'recent_week' ? 'short_term' : timeRange.value

    const [artistsRes, tracksRes, recentRes, currentRes] = await Promise.all([
      doFetch(`http://127.0.0.1:8000/api/top-artists?access_token=${token}&time_range=${rangeForApi}`),
      doFetch(`http://127.0.0.1:8000/api/top-tracks?access_token=${token}&time_range=${rangeForApi}`),
      doFetch(`http://127.0.0.1:8000/api/recently-played?access_token=${token}`),
      doFetch(`http://127.0.0.1:8000/api/currently-playing?access_token=${token}`)
    ])

    if (!artistsRes.ok || !tracksRes.ok || !recentRes.ok) {
      throw new Error('Failed to fetch Spotify data')
    }

    topArtists.value = (await artistsRes.json()).items || []
    topTracks.value = (await tracksRes.json()).items || []
    recentlyPlayed.value = (await recentRes.json()).items || []
    currentlyPlaying.value = await currentRes.json()
  } catch (err) {
    error.value = 'Could not load your Spotify data. Try logging in again.'
    console.error(err)
  } finally {
    loading.value = false
  }
}

async function changeTimeRange(range: TimeRange) {
  timeRange.value = range
  await fetchAllData()
}

function login() {
  window.location.href = 'http://127.0.0.1:8000/api/login'
}

function logout() {
  accessToken.value = null
  refreshToken.value = null
  topArtists.value = []
  topTracks.value = []
  recentlyPlayed.value = []
  currentlyPlaying.value = null
  localStorage.removeItem('spotify_access_token')
  localStorage.removeItem('spotify_refresh_token')
}

function formatDuration(ms: number): string {
  const minutes = Math.floor(ms / 60000)
  const seconds = Math.floor((ms % 60000) / 1000)
  return `${minutes}:${seconds.toString().padStart(2, '0')}`
}

function formatPlayedAt(dateString: string): string {
  return new Date(dateString).toLocaleString()
}
</script>

<template>
  <div class="app">
    <header class="header">
      <h1>Spotify Taste Dashboard</h1>
      <p class="subtitle">Your personal music insights</p>
    </header>

    <main>
      <div v-if="!accessToken" class="login-section">
        <button class="login-btn" @click="login">Login with Spotify</button>
      </div>

      <div v-else class="dashboard">
        <div class="top-bar">
          <div class="status">
            <span class="connected">Connected to Spotify</span>
            <button class="logout-btn" @click="logout">Logout</button>
          </div>

          <div class="time-range">
            <button
              v-for="(label, key) in timeRangeLabels"
              :key="key"
              class="range-btn"
              :class="{ active: timeRange === key }"
              @click="changeTimeRange(key as TimeRange)"
            >
              {{ label }}
            </button>
          </div>
        </div>

        <div v-if="loading" class="skeleton-wrap">
          <div class="skeleton-card" v-for="n in 4" :key="n"></div>
        </div>
        <div v-else-if="error" class="error">{{ error }}</div>

        <template v-else>
          <section class="section">
            <h2>Currently Playing</h2>
            <div v-if="currentlyPlaying?.item" class="now-playing">
              <img
                v-if="currentlyPlaying.item.album.images.length"
                :src="currentlyPlaying.item.album.images[0].url"
                class="now-playing-image"
              />
              <div>
                <p class="now-playing-label">
                  {{ currentlyPlaying.is_playing ? 'Playing now' : 'Paused' }}
                </p>
                <h3>{{ currentlyPlaying.item.name }}</h3>
                <p class="secondary">
                  {{ currentlyPlaying.item.artists.map(a => a.name).join(', ') }}
                </p>
              </div>
            </div>
            <p v-else class="secondary">Nothing is currently playing</p>
          </section>

          <!-- Mainstream Score -->
          <section class="section">
            <h2>Mainstream Score</h2>
            <div class="mainstream-card">
              <div class="mainstream-score">
                <div class="score-number">{{ mainstreamScore.overall }}</div>
                <div class="score-label">{{ mainstreamScore.label }}</div>
              </div>

              <div class="mainstream-details">
                <div class="score-row">
                  <span>Top Artists average</span>
                  <strong>{{ mainstreamScore.artistAvg }}/100</strong>
                </div>
                <div class="score-row">
                  <span>Top Tracks average</span>
                  <strong>{{ mainstreamScore.trackAvg }}/100</strong>
                </div>

                <!-- Visual meter -->
                <div class="score-meter">
                  <div class="meter-track">
                    <div
                      class="meter-fill"
                      :style="{ width: mainstreamScore.overall + '%' }"
                    ></div>
                  </div>
                  <div class="meter-labels">
                    <span>Niche</span>
                    <span>Mainstream</span>
                  </div>
                </div>

                <p class="comparison-text">
                  {{ mainstreamScore.comparison }}
                </p>
                <p class="secondary score-note">
                  Updates with your selected time range using Spotify global popularity scores.
                </p>
              </div>
            </div>
          </section>

          <section class="section">
            <h2>Insights</h2>
            <div class="charts-grid">
              <div class="chart-card">
                <h3>Top Genres</h3>
                <div class="bar-list">
                  <div v-for="item in genreChart" :key="item.name" class="bar-row">
                    <div class="bar-label">{{ item.name }}</div>
                    <div class="bar-track">
                      <div class="bar-fill genre" :style="{ width: item.percent + '%' }">
                        <span>{{ item.value }}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <div class="chart-card">
                <h3>Top Artists by Popularity</h3>
                <div class="bar-list">
                  <div v-for="item in artistPopularityChart" :key="item.name" class="bar-row">
                    <div class="bar-label">{{ item.name }}</div>
                    <div class="bar-track">
                      <div class="bar-fill" :style="{ width: item.percent + '%' }">
                        <span>{{ item.value }}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <div class="chart-card">
                <h3>Top Tracks by Popularity</h3>
                <div class="bar-list">
                  <div v-for="item in trackPopularityChart" :key="item.name" class="bar-row">
                    <div class="bar-label">{{ item.name }}</div>
                    <div class="bar-track">
                      <div class="bar-fill track" :style="{ width: item.percent + '%' }">
                        <span>{{ item.value }}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <div class="chart-card">
                <h3>Recently Played Frequency</h3>
                <div class="bar-list">
                  <div v-for="item in recentFrequencyChart" :key="item.name" class="bar-row">
                    <div class="bar-label">{{ item.name }}</div>
                    <div class="bar-track">
                      <div class="bar-fill recent" :style="{ width: item.percent + '%' }">
                        <span>{{ item.value }}x</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </section>

          <section class="section">
            <h2>Top Artists</h2>
            <div class="artist-grid">
              <div v-for="(artist, index) in topArtists" :key="artist.id" class="artist-card">
                <img
                  v-if="artist.images.length"
                  :src="artist.images[0].url"
                  :alt="artist.name"
                  class="artist-image"
                />
                <div class="artist-info">
                  <span class="rank">#{{ index + 1 }}</span>
                  <h3>{{ artist.name }}</h3>
                  <p class="secondary">
                    {{ artist.genres.slice(0, 2).join(', ') || 'No genres listed' }}
                  </p>
                </div>
              </div>
            </div>
          </section>

          <section class="section">
            <h2>Top Tracks</h2>
            <div class="track-list">
              <div v-for="(track, index) in topTracks" :key="track.id" class="track-row">
                <span class="rank">{{ index + 1 }}</span>
                <img
                  v-if="track.album.images.length"
                  :src="track.album.images[track.album.images.length - 1].url"
                  class="track-image"
                />
                <div class="track-info">
                  <h3>{{ track.name }}</h3>
                  <p class="secondary">
                    {{ track.artists.map(a => a.name).join(', ') }}
                  </p>
                </div>
                <span class="duration">{{ formatDuration(track.duration_ms) }}</span>
              </div>
            </div>
          </section>

          <section class="section">
            <h2>Recently Played</h2>
            <div class="track-list">
              <div
                v-for="(item, index) in (timeRange === 'recent_week' ? recentWeekItems : recentlyPlayed)"
                :key="item.track.id + index"
                class="track-row"
              >
                <img
                  v-if="item.track.album.images.length"
                  :src="item.track.album.images[item.track.album.images.length - 1].url"
                  class="track-image"
                />
                <div class="track-info">
                  <h3>{{ item.track.name }}</h3>
                  <p class="secondary">
                    {{ item.track.artists.map(a => a.name).join(', ') }}
                  </p>
                </div>
                <span class="played-at">{{ formatPlayedAt(item.played_at) }}</span>
              </div>
            </div>
          </section>
        </template>
      </div>
    </main>
  </div>
</template>

<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background-color: #121212;
  color: #fff;
}
.app { max-width: 1100px; margin: 0 auto; padding: 40px 20px; }
.header { margin-bottom: 32px; }
.header h1 { font-size: 32px; font-weight: 700; }
.subtitle { color: #b3b3b3; margin-top: 8px; }
.login-btn {
  background: #1DB954; color: white; border: none; padding: 14px 28px;
  border-radius: 50px; font-size: 16px; font-weight: 600; cursor: pointer;
}
.top-bar {
  display: flex; justify-content: space-between; align-items: center;
  gap: 16px; margin-bottom: 30px; flex-wrap: wrap;
}
.status { display: flex; align-items: center; gap: 12px; }
.connected {
  background: #1DB95433; color: #1DB954; padding: 6px 14px;
  border-radius: 999px; font-size: 14px; font-weight: 600;
}
.logout-btn {
  background: transparent; border: 1px solid #333; color: #b3b3b3;
  padding: 6px 14px; border-radius: 999px; cursor: pointer;
}
.time-range {
  display: flex; gap: 8px; background: #181818; padding: 4px; border-radius: 999px;
  flex-wrap: wrap;
}
.range-btn {
  background: transparent; border: none; color: #b3b3b3;
  padding: 8px 14px; border-radius: 999px; cursor: pointer; font-size: 13px;
}
.range-btn.active { background: #1DB954; color: white; font-weight: 600; }
.section { margin-bottom: 48px; }
.section h2 { font-size: 22px; margin-bottom: 18px; }
.secondary { color: #b3b3b3; font-size: 14px; }
.error { color: #f87171; }
.charts-grid {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 16px;
}
.chart-card { background: #181818; border-radius: 12px; padding: 16px; }
.chart-card h3 { font-size: 15px; margin-bottom: 14px; }
.bar-list { display: flex; flex-direction: column; gap: 10px; }
.bar-row {
  display: grid; grid-template-columns: 110px 1fr; gap: 10px; align-items: center;
}
.bar-label {
  font-size: 12px; color: #b3b3b3; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.bar-track { background: #2a2a2a; border-radius: 999px; overflow: hidden; height: 22px; }
.bar-fill {
  height: 100%; background: #1DB954; border-radius: 999px; display: flex;
  align-items: center; justify-content: flex-end; padding-right: 8px;
  min-width: 28px; font-size: 11px; font-weight: 700;
}
.bar-fill.track { background: #3b82f6; }
.bar-fill.recent { background: #a855f7; }
.bar-fill.genre { background: #f59e0b; }
.artist-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 16px;
}
.artist-card { background: #181818; border-radius: 12px; overflow: hidden; }
.artist-image { width: 100%; aspect-ratio: 1; object-fit: cover; }
.artist-info { padding: 12px; }
.rank { color: #1DB954; font-size: 13px; font-weight: 700; }
.track-list { display: flex; flex-direction: column; gap: 8px; }
.track-row {
  display: flex; align-items: center; gap: 14px; padding: 10px 12px;
  border-radius: 8px; background: #181818;
}
.track-image { width: 48px; height: 48px; border-radius: 4px; object-fit: cover; }
.track-info { flex: 1; min-width: 0; }
.track-info h3 {
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-size: 15px;
}
.duration, .played-at { color: #b3b3b3; font-size: 13px; white-space: nowrap; }
.now-playing {
  display: flex; align-items: center; gap: 20px; background: #181818;
  padding: 20px; border-radius: 12px;
}
.now-playing-image { width: 96px; height: 96px; border-radius: 8px; object-fit: cover; }
.now-playing-label { color: #1DB954; font-size: 13px; font-weight: 600; margin-bottom: 6px; }
.skeleton-wrap {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 16px;
}
.skeleton-card {
  height: 220px; border-radius: 12px;
  background: linear-gradient(90deg, #181818 25%, #222 50%, #181818 75%);
  background-size: 200% 100%; animation: shimmer 1.2s infinite;
}
.mainstream-card {
  display: flex;
  gap: 24px;
  align-items: stretch;
  background: #181818;
  border-radius: 12px;
  padding: 20px;
  flex-wrap: wrap;
}

.mainstream-score {
  min-width: 150px;
  text-align: center;
  background: #121212;
  border-radius: 12px;
  padding: 20px 16px;
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.score-number {
  font-size: 48px;
  font-weight: 800;
  color: #1DB954;
  line-height: 1;
  transition: all 0.25s ease;
}

.score-label {
  margin-top: 10px;
  font-size: 14px;
  font-weight: 700;
  color: #fff;
}

.mainstream-details {
  flex: 1;
  min-width: 240px;
}

.score-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 0;
  border-bottom: 1px solid #2a2a2a;
  font-size: 14px;
}

.score-row strong {
  color: #1DB954;
}

.score-meter {
  margin-top: 16px;
}

.meter-track {
  width: 100%;
  height: 10px;
  background: #2a2a2a;
  border-radius: 999px;
  overflow: hidden;
}

.meter-fill {
  height: 100%;
  background: linear-gradient(90deg, #a855f7, #1DB954);
  border-radius: 999px;
  transition: width 0.35s ease;
}

.meter-labels {
  display: flex;
  justify-content: space-between;
  margin-top: 6px;
  font-size: 12px;
  color: #b3b3b3;
}

.comparison-text {
  margin-top: 14px;
  font-size: 14px;
  font-weight: 600;
  color: #fff;
}

.score-note {
  margin-top: 8px;
  font-size: 13px;
}
@keyframes shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
</style>