'use strict';
const tabs = [...document.querySelectorAll('[data-view]')];
function selectView(view, focus = false) {
  tabs.forEach(tab => { const active = tab.dataset.view === view; tab.setAttribute('aria-selected', String(active)); tab.tabIndex = active ? 0 : -1; if (active && focus) tab.focus(); });
  document.querySelectorAll('[data-side]').forEach(item => item.classList.toggle('selected', item.dataset.side === view));
  document.querySelectorAll('.preview-panel').forEach(panel => { panel.hidden = panel.id !== `panel-${view}`; });
  document.querySelector('#breadcrumb').textContent = ({users: '用户管理', ip: '登录 IP 白名单', quota: '配额与限速', connections: '在线连接'})[view];
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

const quota = document.querySelector('#quota-size');
const speed = document.querySelector('#speed-limit');
function updateQuota() {
  const limit = Number(quota.value), percent = Math.round(18 / limit * 100);
  document.querySelector('#quota-output').textContent = `${limit} GB`;
  document.querySelector('#quota-usage').textContent = `18 / ${limit} GB`;
  document.querySelector('#quota-percent').textContent = `已使用 ${percent}%`;
  document.querySelector('#usage-fill').style.width = `${Math.min(percent, 100)}%`;
  document.querySelector('#usage-fill').classList.toggle('over-limit', percent > 100);
  document.querySelector('.usage-track').setAttribute('aria-valuenow', Math.min(percent, 100));
  document.querySelector('#quota-warning').textContent = percent > 100 ? '示例用量已超过设定上限，请增加容量或清理文件。' : '可按用户设置容量与传输限制。';
}
quota.addEventListener('input', updateQuota);
speed.addEventListener('input', () => { document.querySelector('#speed-output').textContent = `${speed.value} MB/s`; });
updateQuota();
let disconnected = false;
document.querySelector('#demo-disconnect').addEventListener('click', event => {
  disconnected = !disconnected;
  document.querySelector('#demo-session-state').textContent = disconnected ? '已断开（示意）' : '正在上传';
  document.querySelector('#connection-count').textContent = disconnected ? '0 个示例连接' : '1 个示例连接';
  document.querySelector('#session-note').textContent = disconnected ? '示例连接已断开，模拟传输已停止。点击右侧按钮重置演示。' : '发现异常连接时，可以手动断开；正在进行的传输会中断。';
  document.querySelector('.session-progress').classList.toggle('disconnected', disconnected);
  event.currentTarget.textContent = disconnected ? '重置演示' : '断开示例连接';
  notify(disconnected ? '示例连接已断开，未操作真实服务' : '演示已重置');
});
