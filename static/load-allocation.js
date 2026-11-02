/* Convenience proposal only: no aircraft CG, restraint or compatibility approval. */
function proposeAllocation(positions) {
  const standard = Array.from({length:11}, (_, i) => 'M' + String(i + 1).padStart(2, '0'));
  const assignments = Object.fromEntries(positions.map(p => [p.pos, p.pos]));
  if (Object.keys(assignments).length !== positions.length) throw Error('Duplicate manifest positions. Reload the manifest.');
  const movable = positions.filter(p => standard.includes(p.pos));
  if (movable.some(p => !Number.isFinite(p.weight_lbs) || p.weight_lbs < 0)) throw Error('Invalid manifest weight. Reload the manifest.');
  // Place heavier units near the middle of the schematic, alternating outward.
  // This is deliberately not described as a calculated aircraft balance solution.
  const order = [6,5,7,4,8,3,9,2,10,1,11];
  movable.sort((a,b) => b.weight_lbs-a.weight_lbs || a.pos.localeCompare(b.pos));
  movable.forEach((p,i) => { assignments[p.pos] = 'M' + String(order[i]).padStart(2,'0'); });
  return assignments;
}
if (typeof module !== 'undefined') module.exports = {proposeAllocation};
