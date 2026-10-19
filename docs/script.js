'use strict';
const tabs = [...document.querySelectorAll('[data-view]')];
function selectView(view, focus = false) {
  tabs.forEach(tab => { const active = tab.dataset.view === view; tab.setAttribute('aria-selected', String(active)); tab.tabIndex = active ? 0 : -1; if (active && focus) tab.focus(); });
  document.querySelectorAll('.preview-panel').forEach(panel => { panel.hidden = panel.id !== `panel-${view}`; });
  document.querySelector('#breadcrumb').textContent = ({users: '用户管理', ip: '登录 IP 白名单', language: '中文优化'})[view];
}
tabs.forEach((tab, index) => {
  tab.addEventListener('click', () => selectView(tab.dataset.view));
  tab.addEventListener('keydown', event => {
    let next;
    if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
    if (event.key === 'ArrowLeft') next = (index + tabs.length - 1) % tabs.length;
    if (event.key === 'Home') next = 0;
    if (event.key === 'End') next = tabs.length - 1;
    if (next !== undefined) { event.preventDefault(); selectView(tabs[next].dataset.view, true); }
  });
});
selectView('users');
const toast = document.querySelector('#toast');
let toastTimer;
function notify(message) { clearTimeout(toastTimer); toast.textContent = message; toast.classList.add('visible'); toastTimer = setTimeout(() => toast.classList.remove('visible'), 3000); }
document.querySelector('#copy-command').addEventListener('click', async event => {
  const command = document.querySelector('#install-command').textContent;
  try {
    await navigator.clipboard.writeText(command);
    notify('安装命令已复制');
  } catch {
    const range = document.createRange(); range.selectNodeContents(document.querySelector('#install-command'));
    const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range);
    notify('请按 Ctrl+C 或 ⌘C 复制选中的命令');
  }
});
const dialog = document.querySelector('#demo-dialog');
function showDemo(account) {
  document.querySelector('#dialog-title').textContent = account ? `编辑用户 · ${account}` : '新建用户';
  document.querySelector('#dialog-path').textContent = `/srv/sftpgo/data/${account || 'alice'}`;
  dialog.showModal();
}
document.querySelector('#demo-create').addEventListener('click', () => showDemo());
document.querySelectorAll('.edit-demo').forEach(button => button.addEventListener('click', () => showDemo(button.dataset.account)));
document.querySelector('#dialog-install').addEventListener('click', () => dialog.close());
dialog.addEventListener('click', event => { if (event.target === dialog) { const r = dialog.getBoundingClientRect(); if (event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom) dialog.close(); } });
