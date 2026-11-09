import { createContext, useContext } from 'react'

/** Access mode of the server. In the public demo everyone can read and simulate, but only an administrator can write. */
export interface ModeState {
  mode: 'local' | 'demo'
  /** True when this browser cannot change the environment or the scoring configuration. */
  readOnly: boolean
}

export const ModeContext = createContext<ModeState>({ mode: 'local', readOnly: false })
export const useMode = () => useContext(ModeContext)
