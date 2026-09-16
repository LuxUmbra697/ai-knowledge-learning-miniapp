export async function needsDocumentPrivacy() { return false }
export function chooseDocument(): Promise<{ name: string; path: string; size: number; release: () => void } | null> {
  return new Promise(resolve => {
    const input = document.createElement('input')
    input.type = 'file'; input.accept = '.pdf,.docx,.txt,.md'; input.hidden = true
    input.oncancel = () => { input.remove(); resolve(null) }
    input.onchange = () => {
      const file = input.files?.[0]
      input.remove()
      if (!file) { resolve(null); return }
      const path = URL.createObjectURL(file)
      resolve({ name: file.name, size: file.size, path, release: () => URL.revokeObjectURL(path) })
    }
    document.body.append(input)
    input.click()
  })
}
