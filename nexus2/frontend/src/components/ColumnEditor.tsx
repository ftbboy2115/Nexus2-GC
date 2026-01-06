/**
 * ColumnEditor - Drag-and-drop column layout editor
 * 
 * Allows users to reorder and show/hide table columns with persistence.
 */

import { useState, useEffect } from 'react'
import {
    DndContext,
    closestCenter,
    KeyboardSensor,
    PointerSensor,
    useSensor,
    useSensors,
    DragEndEvent,
} from '@dnd-kit/core'
import {
    arrayMove,
    SortableContext,
    sortableKeyboardCoordinates,
    useSortable,
    verticalListSortingStrategy,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import styles from '@/styles/ColumnEditor.module.css'

export interface ColumnConfig {
    id: string
    label: string
    visible: boolean
}

interface SortableColumnProps {
    column: ColumnConfig
    onToggleVisibility: (id: string) => void
}

function SortableColumn({ column, onToggleVisibility }: SortableColumnProps) {
    const {
        attributes,
        listeners,
        setNodeRef,
        transform,
        transition,
        isDragging,
    } = useSortable({ id: column.id })

    const style = {
        transform: CSS.Transform.toString(transform),
        transition,
        opacity: isDragging ? 0.5 : 1,
    }

    return (
        <div
            ref={setNodeRef}
            style={style}
            className={`${styles.columnItem} ${column.visible ? styles.visible : styles.hidden}`}
        >
            <span className={styles.dragHandle} {...attributes} {...listeners}>
                ⋮⋮
            </span>
            <span className={styles.columnLabel}>{column.label}</span>
            <button
                className={styles.visibilityToggle}
                onClick={() => onToggleVisibility(column.id)}
                title={column.visible ? 'Hide column' : 'Show column'}
            >
                {column.visible ? '👁️' : '👁️‍🗨️'}
            </button>
        </div>
    )
}

interface ColumnEditorProps {
    columns: ColumnConfig[]
    onColumnsChange: (columns: ColumnConfig[]) => void
    onSave: () => void
    onCancel: () => void
    onReset: () => void
}

export default function ColumnEditor({
    columns,
    onColumnsChange,
    onSave,
    onCancel,
    onReset,
}: ColumnEditorProps) {
    const sensors = useSensors(
        useSensor(PointerSensor),
        useSensor(KeyboardSensor, {
            coordinateGetter: sortableKeyboardCoordinates,
        })
    )

    function handleDragEnd(event: DragEndEvent) {
        const { active, over } = event

        if (over && active.id !== over.id) {
            const oldIndex = columns.findIndex((c) => c.id === active.id)
            const newIndex = columns.findIndex((c) => c.id === over.id)
            onColumnsChange(arrayMove(columns, oldIndex, newIndex))
        }
    }

    function handleToggleVisibility(id: string) {
        onColumnsChange(
            columns.map((c) =>
                c.id === id ? { ...c, visible: !c.visible } : c
            )
        )
    }

    return (
        <div className={styles.editor}>
            <h3 className={styles.title}>📊 Edit Columns</h3>
            <p className={styles.hint}>Drag to reorder • Click 👁️ to hide/show</p>

            <DndContext
                sensors={sensors}
                collisionDetection={closestCenter}
                onDragEnd={handleDragEnd}
            >
                <SortableContext
                    items={columns.map((c) => c.id)}
                    strategy={verticalListSortingStrategy}
                >
                    <div className={styles.columnList}>
                        {columns.map((column) => (
                            <SortableColumn
                                key={column.id}
                                column={column}
                                onToggleVisibility={handleToggleVisibility}
                            />
                        ))}
                    </div>
                </SortableContext>
            </DndContext>

            <div className={styles.actions}>
                <button className={styles.resetBtn} onClick={onReset}>
                    Reset
                </button>
                <button className={styles.cancelBtn} onClick={onCancel}>
                    Cancel
                </button>
                <button className={styles.saveBtn} onClick={onSave}>
                    Save
                </button>
            </div>
        </div>
    )
}
