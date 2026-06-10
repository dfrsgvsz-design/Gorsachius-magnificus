/**
 * Biodiversity diversity index calculations.
 *
 * Input: an array of species counts, e.g. [12, 5, 3, 8, 1]
 * where each element is the number of individuals of one species.
 */

export function shannonWiener(counts) {
  const N = counts.reduce((s, n) => s + n, 0)
  if (N === 0) return 0
  let H = 0
  for (const n of counts) {
    if (n <= 0) continue
    const p = n / N
    H -= p * Math.log(p)
  }
  return H
}

export function simpson(counts) {
  const N = counts.reduce((s, n) => s + n, 0)
  if (N <= 1) return 0
  let sum = 0
  for (const n of counts) {
    sum += n * (n - 1)
  }
  return 1 - sum / (N * (N - 1))
}

export function simpsonDominance(counts) {
  const N = counts.reduce((s, n) => s + n, 0)
  if (N <= 1) return 0
  let sum = 0
  for (const n of counts) {
    sum += n * (n - 1)
  }
  return sum / (N * (N - 1))
}

export function pielouEvenness(counts) {
  const S = counts.filter((n) => n > 0).length
  if (S <= 1) return 1
  const H = shannonWiener(counts)
  return H / Math.log(S)
}

export function margalefRichness(counts) {
  const N = counts.reduce((s, n) => s + n, 0)
  const S = counts.filter((n) => n > 0).length
  if (N <= 1) return 0
  return (S - 1) / Math.log(N)
}

export function speciesRichness(counts) {
  return counts.filter((n) => n > 0).length
}

export function totalAbundance(counts) {
  return counts.reduce((s, n) => s + n, 0)
}

export function dominanceIndex(counts) {
  const N = counts.reduce((s, n) => s + n, 0)
  if (N === 0) return 0
  const maxN = Math.max(...counts)
  return maxN / N
}

export function bergerParkerIndex(counts) {
  return dominanceIndex(counts)
}

/**
 * Calculate all standard diversity indices from species count data.
 *
 * @param {Array<{species: string, count: number}>} observations
 * @returns {Object} All indices with labels
 */
export function calculateAllIndices(observations) {
  const speciesCounts = {}
  for (const obs of observations) {
    const key = obs.species || obs.scientific_name || obs.species_id || 'unknown'
    speciesCounts[key] = (speciesCounts[key] || 0) + (obs.count || 1)
  }

  const counts = Object.values(speciesCounts)
  const S = speciesRichness(counts)
  const N = totalAbundance(counts)
  const H = shannonWiener(counts)
  const D = simpson(counts)
  const J = pielouEvenness(counts)
  const d = margalefRichness(counts)
  const BP = bergerParkerIndex(counts)

  return {
    speciesRichness: { value: S, label: 'Species Richness', labelZh: '物种丰富度', symbol: 'S' },
    totalAbundance: { value: N, label: 'Total Abundance', labelZh: '总个体数', symbol: 'N' },
    shannonWiener: { value: Number(H.toFixed(4)), label: 'Shannon-Wiener Index', labelZh: 'Shannon-Wiener 指数', symbol: "H'" },
    simpson: { value: Number(D.toFixed(4)), label: 'Simpson Diversity Index', labelZh: 'Simpson 多样性指数', symbol: '1-D' },
    pielouEvenness: { value: Number(J.toFixed(4)), label: 'Pielou Evenness', labelZh: 'Pielou 均匀度指数', symbol: "J'" },
    margalefRichness: { value: Number(d.toFixed(4)), label: 'Margalef Richness Index', labelZh: 'Margalef 丰富度指数', symbol: 'd' },
    bergerParker: { value: Number(BP.toFixed(4)), label: 'Berger-Parker Dominance', labelZh: 'Berger-Parker 优势度', symbol: 'BP' },
    speciesCounts,
    countArray: counts,
  }
}

/**
 * Generate a species abundance table sorted by count (descending).
 */
export function buildSpeciesTable(observations) {
  const rows = {}
  for (const obs of observations) {
    const key = obs.species || obs.scientific_name || obs.species_id || 'unknown'
    if (!rows[key]) {
      rows[key] = {
        scientific_name: obs.scientific_name || key,
        chinese_name: obs.chinese_name || obs.simplified_chinese_name || '',
        english_name: obs.english_name || obs.english_common_name || '',
        taxon_group: obs.taxon_group || '',
        count: 0,
        observations: 0,
      }
    }
    rows[key].count += obs.count || 1
    rows[key].observations += 1
  }

  return Object.values(rows)
    .map((row) => ({
      ...row,
      relative_abundance: 0,
    }))
    .sort((a, b) => b.count - a.count)
    .map((row, _, arr) => {
      const total = arr.reduce((s, r) => s + r.count, 0)
      return { ...row, relative_abundance: total > 0 ? Number((row.count / total * 100).toFixed(2)) : 0 }
    })
}
