import { useRef } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { logger } from '@wolffm/logger/client';
import { HadokuThemeRoot, useHadokuTheme } from '@wolffm/themes';
import { AppHeader } from '@wolffm/task-ui-components';
// The platform's theme tokens and its header: every hadoku.me app loads these.
import '@wolffm/themes/style.css';
import '@wolffm/task-ui-components/theme-picker.css';
import '@wolffm/task-ui-components/app-header.css';
import App from './App';
import { CrashBoundary } from './components/CrashBoundary';
import { startTelemetry } from './telemetry';
import './index.css';

/**
 * hadoku.me's mount contract (hadoku_site's mf-loader): `mount(el, props)` and
 * `unmount(el)`. React, @wolffm/themes, @wolffm/task-ui-components and the
 * logger come from the page's import map (vite.lib.config.ts externalizes
 * them), so this bundle carries only the app.
 */
export interface JobPlatformProps {
  /** The display name, from hadoku_site's spec/categories.json. */
  appName?: string;
  /** The theme key the platform resolved; HadokuThemeRoot owns it from there. */
  theme?: string;
  /** mf-loader's tier for the viewer: 'public' when nobody is signed in. Requests
   * authenticate by the hadoku_session cookie, never by a prop. */
  userType?: string;
  /** Set when mounted inside hadoku.me: the platform header carries the name. */
  embedded?: boolean;
}

function Hosted(props: JobPlatformProps) {
  const containerRef = useRef<HTMLElement>(null);
  return (
    <HadokuThemeRoot theme={props.theme} containerRef={containerRef}>
      <Shell {...props} containerRef={containerRef} />
    </HadokuThemeRoot>
  );
}

function Shell(props: JobPlatformProps & { containerRef: React.RefObject<HTMLElement | null> }) {
  const { theme, isDarkTheme } = useHadokuTheme();
  return (
    <main
      ref={props.containerRef}
      className="jobpulse-host"
      data-theme={theme}
      data-dark-theme={isDarkTheme ? 'true' : 'false'}
    >
      <div className="jobpulse-host__header">
        <AppHeader title={props.appName ?? 'JobPulse'} />
      </div>
      <CrashBoundary>
        <App {...props} theme={theme} embedded />
      </CrashBoundary>
    </main>
  );
}

interface JobPlatformElement extends HTMLElement {
  __root?: Root;
  __stopTelemetry?: () => void;
}

export function mount(el: HTMLElement, props: JobPlatformProps = {}) {
  const root = createRoot(el);
  root.render(<Hosted {...props} />);
  (el as JobPlatformElement).__root = root;
  // Every control and every failed call, to hadoku's service_events via the
  // jobplatform worker's relay (see src/telemetry.ts).
  (el as JobPlatformElement).__stopTelemetry = startTelemetry(el, { app: 'jobpulse' });
  logger.info('[jobpulse] mounted', { theme: props.theme });
}

export function unmount(el: HTMLElement) {
  (el as JobPlatformElement).__stopTelemetry?.();
  (el as JobPlatformElement).__root?.unmount();
  logger.info('[jobpulse] unmounted');
}

export default { mount, unmount };
