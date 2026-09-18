-- Patch 1 / Milestone 0C: additive capability taxonomy (Trade -> Task ->
-- WorkerCapability -> Assessment). No existing table, column, index, or
-- foreign key is altered. Hand-authored to match the DDL `prisma migrate
-- dev` would generate for the schema.prisma changes in this patch — see
-- the Patch 1 report for why this was hand-authored instead of generated
-- (Prisma engine binaries are not reachable in this sandbox).

-- CreateTable
CREATE TABLE "Trade" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "code" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "description" TEXT,
    "isActive" BOOLEAN NOT NULL DEFAULT true,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" DATETIME NOT NULL
);

-- CreateTable
CREATE TABLE "Task" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "tradeId" TEXT NOT NULL,
    "code" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "description" TEXT,
    "safetyQualificationRequired" BOOLEAN NOT NULL DEFAULT false,
    "adjacencyGroup" TEXT,
    "isActive" BOOLEAN NOT NULL DEFAULT true,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" DATETIME NOT NULL,
    CONSTRAINT "Task_tradeId_fkey" FOREIGN KEY ("tradeId") REFERENCES "Trade" ("id") ON DELETE RESTRICT ON UPDATE CASCADE
);

-- CreateTable
CREATE TABLE "WorkerCapability" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "workerId" TEXT NOT NULL,
    "taskId" TEXT NOT NULL,
    "level" INTEGER NOT NULL,
    "provenance" TEXT NOT NULL,
    "confidence" REAL,
    "restrictions" TEXT,
    "lastVerifiedAt" DATETIME,
    "evidenceRef" TEXT,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" DATETIME NOT NULL,
    CONSTRAINT "WorkerCapability_workerId_fkey" FOREIGN KEY ("workerId") REFERENCES "Worker" ("id") ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT "WorkerCapability_taskId_fkey" FOREIGN KEY ("taskId") REFERENCES "Task" ("id") ON DELETE RESTRICT ON UPDATE CASCADE
);

-- CreateTable
CREATE TABLE "Assessment" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "workerCapabilityId" TEXT NOT NULL,
    "type" TEXT NOT NULL,
    "result" TEXT NOT NULL,
    "assessedBy" TEXT,
    "assessedAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "evidenceNotes" TEXT,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Assessment_workerCapabilityId_fkey" FOREIGN KEY ("workerCapabilityId") REFERENCES "WorkerCapability" ("id") ON DELETE CASCADE ON UPDATE CASCADE
);

-- CreateIndex
CREATE UNIQUE INDEX "Trade_code_key" ON "Trade"("code");

-- CreateIndex
CREATE INDEX "Trade_isActive_idx" ON "Trade"("isActive");

-- CreateIndex
CREATE UNIQUE INDEX "Task_code_key" ON "Task"("code");

-- CreateIndex
CREATE INDEX "Task_tradeId_idx" ON "Task"("tradeId");

-- CreateIndex
CREATE INDEX "Task_isActive_idx" ON "Task"("isActive");

-- CreateIndex
CREATE INDEX "WorkerCapability_taskId_idx" ON "WorkerCapability"("taskId");

-- CreateIndex
CREATE UNIQUE INDEX "WorkerCapability_workerId_taskId_key" ON "WorkerCapability"("workerId", "taskId");

-- CreateIndex
CREATE INDEX "Assessment_workerCapabilityId_idx" ON "Assessment"("workerCapabilityId");
