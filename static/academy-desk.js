/* Academy Director desk: draft, edit and publish new Academy material. */
async function loadAcademyDesk(editId = 0) {
  const root = document.getElementById("academyRoot");
  root.innerHTML = '<p class="muted">Loading Academy desk…</p>';
  let items;
  try { items = (await api("/api/staff/academy")).items; }
  catch (e) { root.innerHTML = `<div class="notice err">${esc(e.message)}</div>`; return; }
  const selected = items.find(x => x.id === Number(editId));
  const courses = items.filter(x => x.kind === "course");
  root.innerHTML = `<h1>Academy desk</h1><p class="muted">Create courses, lessons and downloadable resources. Existing 737 cockpit lessons remain available.</p>
    <p><a class="btn ghost" href="/academy/" target="_blank" rel="noopener">Open public Academy</a></p>
    <form id="academyForm" class="panel" style="padding:20px;display:grid;gap:14px">
      <h2>${selected ? "Edit" : "Create"} Academy material</h2>
      <label>Type <select name="kind"><option value="course">Course</option><option value="lesson">Lesson</option><option value="resource">Resource / download</option></select></label>
      <label id="academyParentWrap">Course <select name="course_id"><option value="">Choose a course</option>${courses.map(c => `<option value="${c.id}">${esc(c.title)}</option>`).join("")}</select></label>
      <label>Title <input name="title" maxlength="120" required value="${esc(selected?.title || "")}"></label>
      <label>Short description <textarea name="summary" maxlength="500" rows="2">${esc(selected?.summary || "")}</textarea></label>
      <label>Content <textarea name="body" maxlength="20000" rows="10" placeholder="Separate paragraphs with a blank line.">${esc(selected?.body || "")}</textarea></label>
      <label>Display order <input name="position" type="number" min="0" max="9999" value="${selected?.position || 0}"></label>
      <label><input name="published" type="checkbox" ${selected?.published ? "checked" : ""}> Published (visible on PAC Academy)</label>
      <div class="row"><button class="btn" type="submit">Save material</button><button class="btn ghost" type="button" id="academyClear">New blank item</button></div>
      <p class="muted" style="font-size:13px">Save as a draft, review, then publish. Lessons appear only while their course is published.</p>
      ${selected?.kind === "resource" ? `<label>Attach PDF or image (12 MB max) <input type="file" id="academyFile" accept=".pdf,.png,.jpg,.jpeg,.webp"></label><button class="btn ghost" id="academyUpload" type="button">Upload file</button>${selected.filename ? `<span>Current file: ${esc(selected.filename)}</span>` : ""}` : ""}
    </form><h2 style="margin-top:26px">Your material</h2>
    ${items.length ? `<div class="table-wrap"><table class="fin-table"><thead><tr><th>Type</th><th>Title</th><th>Status</th><th>Order</th><th>Actions</th></tr></thead><tbody>${items.map(x => `<tr><td>${esc(x.kind)}</td><td><b>${esc(x.title)}</b>${x.kind === "lesson" ? `<br><span class="muted">${esc(courses.find(c => c.id === x.course_id)?.title || "Missing course")}</span>` : ""}</td><td>${x.published ? "Published" : "Draft"}</td><td>${x.position}</td><td><button class="btn ghost small" data-academy-edit="${x.id}">Edit</button> <button class="btn ghost small" data-academy-delete="${x.id}">Delete</button></td></tr>`).join("")}</tbody></table></div>` : '<p class="muted">No material yet. Create a course to start.</p>'}`;
  const f = document.getElementById("academyForm");
  f.elements.kind.value = selected?.kind || "course";
  f.elements.course_id.value = selected?.course_id || "";
  const showParent = () => document.getElementById("academyParentWrap").hidden = f.elements.kind.value !== "lesson";
  f.elements.kind.onchange = showParent; showParent();
  document.getElementById("academyClear").onclick = () => loadAcademyDesk();
  f.onsubmit = async e => {
    e.preventDefault();
    const b = { id: selected?.id || 0, kind: f.elements.kind.value, course_id: f.elements.course_id.value,
      title: f.elements.title.value, summary: f.elements.summary.value, body: f.elements.body.value,
      position: f.elements.position.value, published: f.elements.published.checked };
    try { const r = await api("/api/staff/academy", { method: "POST", body: b }); toast("Academy material saved."); loadAcademyDesk(r.item.id); }
    catch (err) { toast(err.message); }
  };
  const upload = document.getElementById("academyUpload");
  if (upload) upload.onclick = async () => {
    const file = document.getElementById("academyFile").files[0]; if (!file) { toast("Choose a file first."); return; }
    const fd = new FormData(); fd.append("file", file);
    try { await apiForm(`/api/staff/academy/${selected.id}/file`, fd); toast("Resource uploaded."); loadAcademyDesk(selected.id); }
    catch (err) { toast(err.message); }
  };
  root.querySelectorAll("[data-academy-edit]").forEach(b => b.onclick = () => loadAcademyDesk(b.dataset.academyEdit));
  root.querySelectorAll("[data-academy-delete]").forEach(b => b.onclick = async () => {
    if (!confirm("Delete this Academy item?")) return;
    try { await api(`/api/staff/academy/${b.dataset.academyDelete}`, { method: "DELETE" }); toast("Academy item deleted."); loadAcademyDesk(); }
    catch (err) { toast(err.message); }
  });
}
