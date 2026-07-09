// Stage: Input Layer
// Checks if project has real, traceable inputs

function validate(project) {
  const inputs = project.inputs || [];
  const hasReal = inputs.some(inp => inp.source && inp.source.trim() && inp.intent);
  const assetCount = (project.assets || []).length;
  return {
    id: 'input_layer',
    label: 'Input layer',
    group: 'inputs',
    status: hasReal ? 'covered' : 'missing',
    detail: hasReal
      ? `${inputs.length} inputs, ${assetCount} assets`
      : 'No real inputs found',
    passed: hasReal
  };
}

module.exports = { validate };