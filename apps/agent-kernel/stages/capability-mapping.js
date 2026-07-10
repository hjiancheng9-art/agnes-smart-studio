// Stage: Capability Mapping
// Checks capability matrix and production maturity

function validate(project) {
  const capabilities = project.capabilityMatrix || null;
  const maturity = project.productionMaturity || {};
  const hasCapabilities = capabilities && Object.keys(capabilities).length > 0;
  const hasMaturity = maturity.level >= 1;
  return {
    id: 'capability_mapping',
    label: 'Capability mapping',
    group: 'readiness',
    status: hasCapabilities && hasMaturity ? 'covered' : 'partial',
    detail: hasCapabilities
      ? `${Object.keys(capabilities).length} capabilities, maturity ${maturity.level || 0}`
      : 'No capability matrix',
    passed: hasCapabilities && hasMaturity
  };
}

module.exports = { validate };