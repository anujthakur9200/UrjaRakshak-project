import { Schema, model } from 'mongoose'
import { IGridEvent } from '../types'

const gridEventSchema = new Schema<IGridEvent>(
  {
    substationId: { type: String, required: true, index: true },
    meterId: { type: String, required: true, index: true },
    energyKwh: { type: Number, required: true },
    timestamp: { type: Date, required: true, default: Date.now, index: true },
    isAnomaly: { type: Boolean, required: true, default: false },
    anomalyScore: { type: Number, required: true, default: 0, min: 0, max: 1 },
    source: { type: String, required: true },
    metadata: { type: Schema.Types.Mixed, default: {} },
  },
  {
    timestamps: true,
    collection: 'grid_events',
  }
)

gridEventSchema.index({ substationId: 1, timestamp: -1 })
gridEventSchema.index({ isAnomaly: 1, timestamp: -1 })

export const GridEvent = model<IGridEvent>('GridEvent', gridEventSchema)
