(function () {
  var go = document.getElementById("go");
  if (!go) return;
  var input = document.getElementById("fq");
  var box = document.getElementById("res");

  async function search() {
    var q = input.value.trim();
    if (!q) return;
    go.disabled = true;
    go.textContent = "Searching…";
    box.textContent = "";
    var url = "https://nominatim.openstreetmap.org/search?format=jsonv2&limit=6&q=" + encodeURIComponent(q);
    if (document.getElementById("ph").checked) url += "&countrycodes=ph";
    try {
      var res = await fetch(url);
      var data = await res.json();
      if (!data.length) { box.textContent = "No results. You can type the details below instead."; return; }
      data.forEach(function (item) {
        var name = item.name || item.display_name.split(",")[0];
        var b = document.createElement("button");
        b.type = "button";
        b.className = "pick";
        b.textContent = "📍 " + name + " — " + item.display_name;
        b.addEventListener("click", function () {
          document.getElementById("company").value = name;
          document.getElementById("location").value = item.display_name;
          box.textContent = "✅ Filled in below. Add the position and save.";
        });
        box.appendChild(b);
      });
    } catch (err) {
      box.textContent = "Search is unavailable right now. You can type the details below.";
    } finally {
      go.disabled = false;
      go.textContent = "Find";
    }
  }

  go.addEventListener("click", search);
  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter") { e.preventDefault(); search(); }
  });
})();
