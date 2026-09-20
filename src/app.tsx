import { createBrowserRouter, Navigate } from 'react-router-dom';
import Shell from './components/Shell';

const config = [{
  Component: Shell,
  children: [
    { index: true, element: <Navigate to="/library" replace /> },
    { path: 'library', lazy: async () => ({ Component: (await import('./pages/Library')).default }) },
    { path: 'chat', lazy: async () => ({ Component: (await import('./pages/Chat')).default }) },
    { path: 'documents/:id', lazy: async () => ({ Component: (await import('./pages/DocumentDetail')).default }) },
    { path: 'settings', lazy: async () => ({ Component: (await import('./pages/Settings')).default }) },
    { path: 'notes', lazy: async () => ({ Component: (await import('./pages/Notes')).default }) },
    { path: '*', element: <Navigate to="/library" replace /> },
  ],
}];

export const router = createBrowserRouter(config);
