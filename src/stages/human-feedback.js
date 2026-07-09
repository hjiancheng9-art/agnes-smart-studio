// Stage: Human Feedback
// Checks calibration and review records

function validate(project) {
  const maturity = project.productionMaturity || {};
  const cal = maturity.calibration || {};
  const records = cal.records || {};
  const totalObservations = Object.values(records).reduce((sum, r) => sum + (r.attempts || 0), 0);
  const calibratedCapabilities = Object.values(records).filter(r => r.status === 'calibrated').length;
  const hasFeedback = totalObservations > 0;
  return {
    id: 'human_feedback',
    label: 'Human feedback',
    group: 'readiness',
    status: calibratedCapabilities >= 3 ? 'covered' : hasFeedback ? 'partial' : 'missing',
    detail: hasFeedback
      ? `${totalObservations} observations, ${calibratedCapabilities} calibrated`
      : 'No feedback records',
    passed: calibratedCapabilities >= 3
  };
}

module.exports = { validate };