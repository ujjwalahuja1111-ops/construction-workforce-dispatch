import { Response } from 'express';
import { CapabilityService, selfDeclareCapabilitySchema } from '../services/capability.service';
import { AuthedRequest } from '../middleware/auth';

/**
 * Patch 2 — Worker Capability API (Self-Declaration).
 *
 * Mounted on the EXISTING `worker.routes.ts` router, which already applies
 * `requireAuth` + `requireRole(Role.WORKER)` to everything it owns — no new
 * middleware or auth boundary is introduced here. The acting worker is
 * always `req.auth.sub` (the JWT subject); nothing in this file, the route,
 * or the service ever reads a `workerId` from the request.
 */

export { selfDeclareCapabilitySchema };

export const WorkerCapabilityController = {
  async selfDeclare(req: AuthedRequest, res: Response) {
    const { capability, created } = await CapabilityService.selfDeclare(req.auth!.sub, req.body);
    res.status(created ? 201 : 200).json({ capability: shapeCapability(capability) });
  },

  async list(req: AuthedRequest, res: Response) {
    const capabilities = await CapabilityService.listForAuthenticatedWorker(req.auth!.sub);
    res.json({ capabilities: capabilities.map(shapeCapability) });
  },
};

/**
 * Shared response shaping per Patch 2 contract §3 — never exposes
 * `workerId` (redundant — it's always the caller) and flattens
 * `task.trade.code` to `task.tradeCode` for a smaller payload.
 */
function shapeCapability(capability: {
  id: string;
  taskId: string;
  level: number;
  provenance: string;
  createdAt: Date;
  updatedAt: Date;
  task: { code: string; name: string; trade: { code: string } };
}) {
  return {
    id: capability.id,
    taskId: capability.taskId,
    level: capability.level,
    provenance: capability.provenance,
    createdAt: capability.createdAt,
    updatedAt: capability.updatedAt,
    task: {
      code: capability.task.code,
      name: capability.task.name,
      tradeCode: capability.task.trade.code,
    },
  };
}
