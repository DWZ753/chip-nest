interface Window {
  chipnest?: {
    chooseBackupDirectory: () => Promise<string | null>
  }
}
