import express from 'express';
import cors from 'cors';
import path from 'path';
import http from 'http';
import { WebSocketServer, WebSocket } from 'ws';
import regionsRouter from './routes/regions';
import predictionsRouter from './routes/predictions';

export interface AppServer {
  httpServer: http.Server;
  wsClients: Set<WebSocket>;
  start: (port: number) => void;
}

export function createServer(): AppServer {
  const app = express();

  app.use(cors());
  app.use(express.json());

  // Serve React SPA static files
  const publicDir = path.join(__dirname, '..', 'public');
  app.use(express.static(publicDir));

  // API routes
  app.use('/api/regions', regionsRouter);
  app.use('/api/predictions', predictionsRouter);

  // Fallback: serve index.html for any non-API route (SPA routing)
  app.get('*', (_req, res) => {
    res.sendFile(path.join(publicDir, 'index.html'));
  });

  const httpServer = http.createServer(app);

  // WebSocket server for live map refresh
  const wss = new WebSocketServer({ server: httpServer });
  const wsClients = new Set<WebSocket>();

  wss.on('connection', (ws: WebSocket) => {
    wsClients.add(ws);
    ws.on('close', () => wsClients.delete(ws));
    ws.on('error', () => wsClients.delete(ws));
  });

  function start(port: number): void {
    httpServer.listen(port, () => {
      console.log(`Dashboard Service listening on port ${port}`);
    });
  }

  return { httpServer, wsClients, start };
}
