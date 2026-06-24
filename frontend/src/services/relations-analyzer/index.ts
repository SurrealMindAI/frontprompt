/**
 * relations-analyzer barrel — DOM-Post-Processing → Relation-objects.
 *
 * Konsumiert von region-draft.commit() nach dem region-scan: analysiert die
 * DOM-Beziehungen der gescannten picks und derived ``part_of``/``relates_to``
 * Relations. Caller persistiert die Relations via inspector.submitRelation.
 */
export { analyzeDomRelations } from './relations-analyzer';
export type { PickElementRef } from './relations-analyzer';
