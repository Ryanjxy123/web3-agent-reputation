import type { CapabilityCoverage, EvaluationReport } from './contracts'

export function businessCapabilities(report: EvaluationReport): CapabilityCoverage[] {
  return (report.capabilities ?? []).filter(capability => report.samples.some(item =>
    item.capability_id === capability.capability_id && ['functional', 'behavioral'].includes(item.sample.purpose)))
}

export function capabilityDimension(report: EvaluationReport, capability: CapabilityCoverage, purpose: 'availability' | 'functional' | 'behavioral') {
  const samples = report.samples.filter(item => item.sample.purpose === purpose)
  // Report scores apply to one capability only when every sample in that dimension is explicitly bound to it.
  return samples.length > 0 && samples.every(item => item.capability_id === capability.capability_id)
    ? report.scores[purpose] : null
}

export function capabilityKey(capability: CapabilityCoverage): string {
  return capability.checker_id ?? `${capability.protocol}:${capability.operation}`
}
