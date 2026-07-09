// Stage: Multi-modal Assembly
// Checks final assembly readiness

function validate(project) {
  const maturity = project.productionMaturity || {};
  const assembly = maturity.assembly || {};
  const outputs = project.outputs || [];
  const hasAssembly = assembly.status === 'ready' || assembly.status === 'completed';
  const multiModalReady = outputs.some(o => o.format === 'video' || o.format === 'multimodal');
  return {
    id: 'multi_modal_assembly',
    label: 'Multi-modal assembly',
    group: 'production',
    status: hasAssembly || multiModalReady ? 'covered' : 'partial',
    detail: hasAssembly
      ? `Assembly ${assembly.status}, ${outputs.length} outputs`
      : 'Assembly not ready',
    passed: hasAssembly || multiModalReady
  };
}

module.exports = { validate };