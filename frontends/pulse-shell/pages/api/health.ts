import type { NextApiRequest, NextApiResponse } from 'next'
import logger from '../../lib/logger'

export default function handler(_req: NextApiRequest, res: NextApiResponse) {
  logger.debug('health check')
  res.status(200).json({ status: 'ok', service: 'pulse-shell' })
}
