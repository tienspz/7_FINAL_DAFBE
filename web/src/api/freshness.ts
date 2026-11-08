import type { Freshness } from './types';

export function selectLatestFreshness(
  sseFreshness: Freshness | null,
  healthFreshness: Freshness | null | undefined,
): Freshness | null {
  if (!sseFreshness) return healthFreshness ?? null;
  if (!healthFreshness) return sseFreshness;

  const sseGeneratedAt = Date.parse(sseFreshness.generated_at ?? '');
  const healthGeneratedAt = Date.parse(healthFreshness.generated_at ?? '');

  if (Number.isFinite(sseGeneratedAt) && Number.isFinite(healthGeneratedAt)) {
    if (sseGeneratedAt !== healthGeneratedAt) {
      return sseGeneratedAt > healthGeneratedAt ? sseFreshness : healthFreshness;
    }
  } else if (Number.isFinite(sseGeneratedAt) !== Number.isFinite(healthGeneratedAt)) {
    return Number.isFinite(healthGeneratedAt) ? healthFreshness : sseFreshness;
  }

  const sseAge = sseFreshness.age_seconds;
  const healthAge = healthFreshness.age_seconds;
  if (sseAge === null) return healthFreshness;
  if (healthAge === null) return sseFreshness;
  return healthAge <= sseAge ? healthFreshness : sseFreshness;
}
