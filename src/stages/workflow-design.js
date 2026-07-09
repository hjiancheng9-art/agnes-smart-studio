// Stage: Workflow Design
// Checks workflow and operations governance

function validate(project) {
  const ops = project.operationsGovernance || {};
  const hasWorkflow = ops.workflowStatus === 'approved' || ops.workflowStatus === 'active';
  const hasTemplates = Object.keys(ops.templates || {}).length > 0;
  const shotsCount = (project.shots || []).length;
  return {
    id: 'workflow_design',
    label: 'Workflow design',
    group: 'design',
    status: hasWorkflow ? 'covered' : 'partial',
    detail: hasWorkflow
      ? `Workflow ${ops.workflowStatus}, ${shotsCount} shots`
      : 'Workflow not approved',
    passed: hasWorkflow && hasTemplates
  };
}

module.exports = { validate };