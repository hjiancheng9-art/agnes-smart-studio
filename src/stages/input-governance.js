// Stage: Input Governance
// Validates input quality and showrunner assignment

function validate(project) {
  const inputs = project.inputs || [];
  const allValid = inputs.length > 0 && inputs.every(inp => inp.validation?.status !== 'failed');
  const hasShowrunner = !!project.showrunner;
  return {
    id: 'input_governance',
    label: 'Input governance',
    group: 'inputs',
    status: allValid && hasShowrunner ? 'covered' : 'missing',
    detail: allValid
      ? `${inputs.length} inputs validated, showrunner: ${project.showrunner || 'none'}`
      : 'Validation incomplete or showrunner missing',
    passed: allValid && hasShowrunner
  };
}

module.exports = { validate };