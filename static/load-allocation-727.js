/* Schematic proposal only; no CG, restraint, floor or separation approval. */
function proposeAllocation(positions) {
  const standard = Array.from({length:12}, (_, i) => 'M' + String(i + 1).padStart(2, '0'));
  const assignments = Object.fromEntries(positions.map(p => [p.pos, p.pos]));
  if (Object.keys(assignments).length !== positions.length) throw Error('Duplicate manifest positions. Reload the manifest.');
  const movable = positions.filter(p => standard.includes(p.pos));
  if (movable.some(p => !Number.isFinite(p.weight_lbs) || p.weight_lbs < 0)) throw Error('Invalid manifest weight. Reload the manifest.');
  const order = [6,7,5,8,4,9,3,10,2,11,1,12];
  movable.sort((a,b) => b.weight_lbs-a.weight_lbs || a.pos.localeCompare(b.pos));
  movable.forEach((p,i) => { assignments[p.pos] = standard[order[i]-1]; });
  return assignments;
}
if (typeof module !== 'undefined') module.exports = {proposeAllocation};
