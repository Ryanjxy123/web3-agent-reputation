import type { AgentProfile, AgentSummary } from './contracts'

export const roleLabels: Record<AgentProfile['role'], string> = {
  'asset-execution': '链上资产操作',
  'chain-query': '链上数据查询',
  'research-delivery': '研究与预测交付',
  unverified: '业务待核实',
}

const chains: Record<number, string> = {
  1: 'Ethereum', 10: 'Optimism', 56: 'BNB Chain', 100: 'Gnosis', 137: 'Polygon',
  8453: 'Base', 42161: 'Arbitrum', 42220: 'Celo', 43114: 'Avalanche', 5000: 'Mantle',
}

export function chainName(chainId: number): string {
  return chains[chainId] ?? `链 ${chainId}`
}

export function businessSummary(agent: AgentSummary): string {
  return agent.profile?.business_summary || '尚未核实这名 Agent 的具体业务功能，现有评分范围请查看报告。'
}

export function businessRole(agent: AgentSummary): AgentProfile['role'] {
  return agent.profile?.role ?? 'unverified'
}

export function executionChains(agent: AgentSummary): string {
  return agent.profile?.execution_chain_ids.length
    ? agent.profile.execution_chain_ids.map(chainName).join('、') : '业务链待核实'
}

export function profileStatus(profile: AgentProfile): string {
  return { verified: '已有来源核验', declared: '已记录功能声明', unverified: '资料待核实' }[profile.evidence_status]
}

export function isOlasService(agent: AgentSummary): boolean {
  return agent.registration_reference.split(':')[2]?.toLowerCase() === '0x9338b5153ae39bb89f50468e608ed9d764b755fd'
}

export function registrationType(agent: AgentSummary): string {
  if (isOlasService(agent)) return 'Olas Service Registry'
  return agent.registration_reference.split(':')[2]?.toLowerCase() === '0x8004a169fb4a3325136eb29fa0ceb6d2e539a432'
    ? 'ERC-8004 身份注册' : '注册类型待核实'
}

export function supportsSubmission(agent: AgentSummary): boolean {
  return agent.registration_reference.split(':')[2]?.toLowerCase() === '0x8004a169fb4a3325136eb29fa0ceb6d2e539a432'
}
