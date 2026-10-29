import { createRoot, type Root } from 'react-dom/client';
import App from './App';
import './index.css';

export interface JobPlatformProps {
  /**
   * Display name resolved by parent host (e.g. hadoku.me), defaults to 'JobPulse' standalone.
   */
  appName?: string;
  /**
   * Active theme key from @wolffm/themes when mounted in a host container.
   */
  theme?: string;
  /**
   * Viewer tier ('public' | 'friend' | 'service' | 'admin').
   */
  userType?: string;
  /**
   * Optional user identity for multi-tenant profile scoping.
   */
  userId?: string;
}

interface JobPlatformElement extends HTMLElement {
  __root?: Root;
}

export function mount(el: HTMLElement, props: JobPlatformProps = {}) {
  const root = createRoot(el);
  root.render(<App {...props} />);
  (el as JobPlatformElement).__root = root;
}

export function unmount(el: HTMLElement) {
  (el as JobPlatformElement).__root?.unmount();
}

export default { mount, unmount };
