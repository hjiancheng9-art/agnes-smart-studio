// src/stages/index.js — Stage module aggregator
// Each stage validates one layer of the pipeline

const inputLayer = require('./input-layer');
const inputGovernance = require('./input-governance');
const workflowDesign = require('./workflow-design');
const capabilityMapping = require('./capability-mapping');
const humanFeedback = require('./human-feedback');
const outputProduction = require('./output-production');
const multiModalAssembly = require('./multi-modal-assembly');

const STAGES = {
  input_layer: inputLayer,
  input_governance: inputGovernance,
  workflow_design: workflowDesign,
  capability_mapping: capabilityMapping,
  human_feedback: humanFeedback,
  output_production: outputProduction,
  multi_modal_assembly: multiModalAssembly
};

const CORE_LAYER_DEFS = [
  ['input_layer', 'Input layer', 'inputs'],
  ['input_governance', 'Input governance', 'inputs'],
  ['workflow_design', 'Workflow design', 'design'],
  ['capability_mapping', 'Capability mapping', 'readiness'],
  ['human_feedback', 'Human feedback', 'readiness'],
  ['output_production', 'Output production', 'production'],
  ['multi_modal_assembly', 'Multi-modal assembly', 'production']
];

function validateAll(project) {
  return CORE_LAYER_DEFS.map(([id]) => {
    const stage = STAGES[id];
    return stage ? stage.validate(project) : {
      id, status: 'unknown', detail: 'No stage handler', passed: false
    };
  });
}

module.exports = { STAGES, CORE_LAYER_DEFS, validateAll };