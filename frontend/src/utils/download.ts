/** 下载当前生成的文件，保存完成后释放临时地址。 */
export function download_file(name: string, content: string, type: string) {
  const url = URL.createObjectURL(new Blob([content], { type }))
  const link = document.createElement('a')
  link.href = url
  link.download = name
  document.body.appendChild(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

/** CSV 文本加引号，防止名称或料号被表格程序执行为公式。 */
export function csv_content(rows: (string | number)[][]): string {
  return '\uFEFF' + rows.map(row => row.map(value => {
    if (typeof value === 'number') return String(value)
    const safe = /^[\s]*[=+@-]/.test(value) ? "'" + value : value
    return '"' + safe.replace(/"/g, '""') + '"'
  }).join(',')).join('\r\n')
}
