// Stage: Output Production
// Checks output assets and production shots

function validate(project) {
  const shots = project.shots || [];
  const outputs = project.outputs || [];
  const hasShots = shots.some(s => s.status === 'rendered' || s.status === 'completed');
  const hasOutputs = outputs.length > 0;
  return {
    id: 'output_production',
    label: 'Output production',
    group: 'production',
    status: hasShots || hasOutputs ? 'covered' : 'partial',
    detail: hasShots
      ? `${shots.filter(s => s.status === 'rendered' || s.status === 'completed').length} rendered, ${outputs.length} outputs`
      : 'No rendered shots',
    passed: hasShots
  };
}

module.exports = { validate };