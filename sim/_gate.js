(function () {
  // 공직선거법 108조 — 6/3 18:00 KST 전엔 콘텐츠 숨김.
  // ?preview=newtamsa-2026 으로 운영자 검증 가능.
  var RELEASE_AT = Date.parse('2026-06-03T18:00:00+09:00');
  var params = new URLSearchParams(location.search);
  var preview = params.get('preview') === 'newtamsa-2026';
  var now = Date.now();
  var locked = now < RELEASE_AT && !preview;

  document.addEventListener('DOMContentLoaded', function () {
    var lock = document.getElementById('sim-gate-lock');
    var content = document.getElementById('sim-gate-content');
    if (!lock || !content) return;
    if (locked) {
      content.style.display = 'none';
      lock.style.display = 'block';
      var diff = RELEASE_AT - now;
      var d = Math.floor(diff / 86400000);
      var h = Math.floor((diff % 86400000) / 3600000);
      var m = Math.floor((diff % 3600000) / 60000);
      var label = document.getElementById('sim-gate-countdown');
      if (label) {
        if (d > 0) label.textContent = 'D-' + d + ' (' + d + '일 ' + h + '시간 ' + m + '분)';
        else if (h > 0) label.textContent = '' + h + '시간 ' + m + '분 후 공개';
        else label.textContent = m + '분 후 공개';
      }
    } else {
      lock.style.display = 'none';
      content.style.display = 'block';
      if (preview) {
        var banner = document.createElement('div');
        banner.style.cssText = 'background:#fff8e3;border-left:4px solid #b8860b;padding:8px 14px;margin-bottom:12px;font-size:0.82rem;color:#8b6500;font-weight:600';
        banner.textContent = '⚠️ 미리보기 모드 — 외부 공개 금지. 운영자 검증용만.';
        content.insertBefore(banner, content.firstChild);
      }
    }
  });
})();
