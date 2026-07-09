// src/agent-kernel.js — Pipeline kernel coordinator
// Refactored: layer validations extracted to src/stages/

const { buildProfessionalPlaybook, professionalSummary } = require('./professional-team');
const { CORE_LAYER_DEFS, validateAll } = require('./stages');

function flatAssets(project) {
  const assets = project.assets || [];
  return assets.map(a => typeof a === 'string' ? { path: a } : a);
}

function hasRealInputs(project) {
  return (project.inputs || []).some(inp => inp.source && inp.source.trim() && inp.intent);
}

function hasAssetSet(project) {
  return (project.assets || []).length > 0 || (project.inputs || []).length > 0;
}

function layerStatus(project, id) {
  const layers = project.coverage?.layers || [];
  const found = layers.find(l => l.id === id);
  return found?.status || 'missing';
}

function groupCoverage(layers) {
  const groups = {};
  for (const layer of layers) {
    if (!groups[layer.group]) {
      groups[layer.group] = { total: 0, covered: 0 };
    }
    groups[layer.group].total += 1;
    if (layer.status === 'covered') groups[layer.group].covered += 1;
  }
  for (const group of Object.values(groups)) {
    group.percent = group.total ? Math.round((group.covered / group.total) * 100) : 0;
  }
  return groups;
}

function buildAgentKernel(project) {
  const assets = flatAssets(project);
  const shots = project.shots || [];
  const ops = project.operationsGovernance || {};
  const maturity = project.productionMaturity || {};
  const capabilities = project.capabilityMatrix || null;

  // Use extracted stages for layer validation
  const layers = validateAll(project);

  // Compute coverage
  const totalLayers = layers.length;
  const coveredLayers = layers.filter(l => l.status === 'covered').length;
  const percent = totalLayers ? Math.round((coveredLayers / totalLayers) * 100) : 0;

  // Professional team
  const playbook = buildProfessionalPlaybook(project);
  const pSummary = professionalSummary(playbook);

  // Check calibration
  const cal = maturity.calibration || {};
  const records = cal.records || {};
  const totalObservations = Object.values(records).reduce((sum, r) => sum + (r.attempts || 0), 0);
  const calibratedCapabilities = Object.values(records).filter(r => r.status === 'calibrated').length;

  const kernel = {
    id: project.id || 'kernel',
    status: percent >= 80 ? 'stable' : percent >= 40 ? 'developing' : 'bootstrapping',
    version: project.version || '0.1.0',
    coverage: {
      percent,
      covered: coveredLayers,
      total: totalLayers,
      layers,
      groups: groupCoverage(layers)
    },
    calibration: {
      status: calibratedCapabilities >= 5 ? 'active' : calibratedCapabilities > 0 ? 'seeding' : 'cold_start',
      calibratedCapabilities,
      totalObservations
    },
    professionalPlaybook: playbook,
    professionalSummary: pSummary,
    snapshot: {
      input_count: (project.inputs || []).length,
      asset_count: assets.length,
      shot_count: shots.length,
      workflow: ops.workflowStatus || 'draft',
      showrunner: project.showrunner || 'none',
      calibration_records: totalObservations,
      script_recreation: `${project.bible?.recreation?.beats?.length || 0} beats`,
      knowledge_base: project.bible?.creativeDirection?.knowledgeLayer?.status || '',
      creative_direction: project.bible?.creativeDirection?.creativeLayer?.genre || '',
      prompt_templates: `${Object.keys(project.bible?.creativeDirection?.promptTemplateLayer?.templates || {}).length} templates`,
      prompt_knowledge_routing: project.promptKnowledgeAudit?.status || 'audit pending'
    }
  };

  return kernel;
}

function kernelSummary(kernel) {
  return {
    status: kernel?.status || 'missing',
    percent: kernel?.coverage?.percent || 0,
    covered: kernel?.coverage?.covered || 0,
    total: kernel?.coverage?.total || 0,
    professionalScore: kernel?.professionalSummary?.score || 0,
    professionalStatus: kernel?.professionalSummary?.status || 'missing'
  };
}

module.exports = {
  CORE_LAYER_DEFS,
  buildAgentKernel,
  kernelSummary
};