import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import time
import os
from typing import Dict, List, Any, Optional
import threading
import subprocess

from config import get_config
from config.anpr_config import ANPRBatchConfig
from db import get_db, ANPRDatabaseIntegration
from batch_processing.batch_processor import ModernBatchProcessor


def show_batch_processing():
    """Main batch processing dashboard."""
    st.title("🔄 Batch Processing Dashboard")
    
    config = get_config()
    db = get_db()
    db_integration = ANPRDatabaseIntegration(db)
    
    # Configuration Section
    with st.expander("⚙️ Processing Configuration", expanded=True):
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.subheader("Input Settings")
            input_dirs = st.text_area(
                "Input Directories", 
                placeholder="Enter paths, one per line\n/mnt/iss_media/CAM_14\n/mnt/iss_media/CAM_16",
                height=100
            )
            video_ext = st.selectbox(
                "Video Extension", 
                options=[".issvd", ".mp4", ".avi", ".mkv"],
                index=0
            )
            
        with col2:
            st.subheader("Worker Configuration")
            cpu_workers = st.slider("CPU Workers", 1, 16, config.anpr_batch.cpu_workers)
            gpu_workers = st.slider("GPU Workers", 1, 8, config.anpr_batch.gpu_workers)
            ffmpeg_gpu_workers = st.slider("FFmpeg GPU Workers", 0, 4, config.anpr_batch.ffmpeg_gpu_workers)
            
        with col3:
            st.subheader("Processing Settings")
            confidence = st.slider("Confidence Threshold", 0.1, 1.0, config.anpr_batch.confidence_threshold)
            frame_skip = st.slider("Frame Skip", 1, 20, config.anpr_batch.frame_skip)
            timeout = st.slider("Timeout (minutes)", 10, 180, config.anpr_batch.process_timeout // 60)
    
    # Control Section
    st.subheader("🎮 Process Control")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        if st.button("🚀 Start Batch Processing", type="primary", use_container_width=True):
            if not input_dirs.strip():
                st.error("Please specify input directories")
            else:
                directories = [d.strip() for d in input_dirs.strip().split('\n') if d.strip()]
                batch_config = ANPRBatchConfig(
                    input_directories=directories,
                    video_extension=video_ext,
                    cpu_workers=cpu_workers,
                    gpu_workers=gpu_workers,
                    ffmpeg_gpu_workers=ffmpeg_gpu_workers,
                    confidence_threshold=confidence,
                    frame_skip=frame_skip,
                    process_timeout=timeout * 60
                )
                
                if start_batch_processing(batch_config):
                    st.success("Batch processing started!")
                    st.rerun()
                else:
                    st.error("Failed to start batch processing")
    
    with col2:
        if st.button("⏹️ Stop Processing", use_container_width=True):
            if stop_batch_processing():
                st.success("Batch processing stopped!")
                st.rerun()
            else:
                st.warning("No active processing to stop")
    
    with col3:
        if st.button("📊 Refresh Status", use_container_width=True):
            st.rerun()
    
    with col4:
        if st.button("🗑️ Clean Logs", use_container_width=True):
            if clean_old_logs():
                st.success("Old logs cleaned!")
    
    # Status and Monitoring
    show_batch_status(db_integration)
    show_processing_metrics(db_integration)
    show_recent_results(db_integration)


def start_batch_processing(config: ANPRBatchConfig) -> bool:
    """Start batch processing in background."""
    try:
        # Validate directories exist
        missing_dirs = [d for d in config.input_directories if not os.path.exists(d)]
        if missing_dirs:
            st.error(f"Missing directories: {', '.join(missing_dirs)}")
            return False
        
        # Start processing in separate thread to avoid blocking UI
        def run_processing():
            try:
                processor = ModernBatchProcessor()
                processor.process_videos_dual_pipeline(config)
            except Exception as e:
                st.error(f"Processing failed: {e}")
        
        thread = threading.Thread(target=run_processing, daemon=True)
        thread.start()
        return True
        
    except Exception as e:
        st.error(f"Failed to start processing: {e}")
        return False


def stop_batch_processing() -> bool:
    """Stop active batch processing."""
    try:
        # Use the manage_videos.sh script to stop processing
        script_path = os.path.join("batch_processing", "manage_videos.sh")
        if os.path.exists(script_path):
            result = subprocess.run(["bash", script_path, "stop"], 
                                  capture_output=True, text=True)
            return result.returncode == 0
        return False
    except Exception as e:
        st.error(f"Failed to stop processing: {e}")
        return False


def clean_old_logs() -> bool:
    """Clean old log files."""
    try:
        db = get_db()
        db_integration = ANPRDatabaseIntegration(db)
        db_integration.cleanup_old_data(days_to_keep=7)
        return True
    except Exception as e:
        st.error(f"Failed to clean logs: {e}")
        return False


def show_batch_status(db_integration: ANPRDatabaseIntegration):
    """Show current batch processing status."""
    st.subheader("📈 Processing Status")
    
    session_status = db_integration.get_current_batch_session_status()
    
    if session_status:
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1:
            status_color = {
                'RUNNING': '🟢',
                'COMPLETED': '✅', 
                'FAILED': '❌',
                'CANCELLED': '⚠️'
            }.get(session_status['status'], '❓')
            st.metric("Status", f"{status_color} {session_status['status']}")
            
        with col2:
            processed = session_status.get('processed_files', 0)
            total = session_status.get('total_files', 0)
            st.metric("Progress", f"{processed}/{total}")
            
        with col3:
            rate = session_status.get('processing_rate', 0)
            st.metric("Processing Rate", f"{rate:.1f} files/min")
            
        with col4:
            eta_seconds = session_status.get('eta_seconds', 0)
            if eta_seconds > 0:
                eta_minutes = eta_seconds / 60
                eta_str = f"{eta_minutes:.0f}m" if eta_minutes > 1 else f"{eta_seconds:.0f}s"
            else:
                eta_str = "N/A"
            st.metric("ETA", eta_str)
            
        with col5:
            success = session_status.get('success_files', 0)
            if processed > 0:
                success_rate = success / processed * 100
                st.metric("Success Rate", f"{success_rate:.1f}%")
            else:
                st.metric("Success Rate", "N/A")
        
        # Progress bar
        if total > 0:
            progress = processed / total
            st.progress(progress)
            
            # Time tracking
            start_time = datetime.fromisoformat(session_status['start_time'])
            elapsed = datetime.now() - start_time
            st.caption(f"Started: {start_time.strftime('%Y-%m-%d %H:%M:%S')} "
                      f"(Running for {elapsed})")
        
        # Session details
        with st.expander("📋 Session Details"):
            col1, col2 = st.columns(2)
            
            with col1:
                st.write("**Session ID:**", session_status['session_id'])
                st.write("**Input Directories:**")
                dirs = session_status.get('input_directories', '').split(',')
                for d in dirs:
                    if d.strip():
                        st.write(f"  • {d.strip()}")
            
            with col2:
                config_snapshot = session_status.get('config_snapshot', '{}')
                try:
                    import json
                    config_data = json.loads(config_snapshot)
                    st.write("**Configuration:**")
                    st.write(f"  • CPU Workers: {config_data.get('cpu_workers', 'N/A')}")
                    st.write(f"  • GPU Workers: {config_data.get('gpu_workers', 'N/A')}")
                    st.write(f"  • Confidence: {config_data.get('confidence_threshold', 'N/A')}")
                except:
                    st.write("**Configuration:** Error parsing")
        
        # Real-time log (if running)
        if session_status['status'] == 'RUNNING':
            with st.container():
                st.subheader("🔍 Live Processing Log")
                log_placeholder = st.empty()
                show_realtime_log(log_placeholder, session_status['session_id'])
    
    else:
        st.info("No active batch processing session")
        
        # Show recent sessions
        active_sessions = db_integration.get_active_sessions()
        if active_sessions:
            st.write("**Recent Sessions:**")
            sessions_df = pd.DataFrame([
                {
                    'Session ID': s['session_id'][:8] + '...',
                    'Status': s['status'],
                    'Started': datetime.fromisoformat(s['start_time']).strftime('%Y-%m-%d %H:%M'),
                    'Files': f"{s.get('processed_files', 0)}/{s.get('total_files', 0)}"
                }
                for s in active_sessions[:5]
            ])
            st.dataframe(sessions_df, use_container_width=True)


def show_processing_metrics(db_integration: ANPRDatabaseIntegration):
    """Show processing performance metrics."""
    st.subheader("📊 Performance Metrics")
    
    # Time range selector
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("Start Date", datetime.now() - timedelta(days=7))
    with col2:
        end_date = st.date_input("End Date", datetime.now())
    
    if start_date <= end_date:
        # Get metrics for the selected range
        start_datetime = datetime.combine(start_date, datetime.min.time())
        end_datetime = datetime.combine(end_date, datetime.max.time())
        
        metrics = db_integration.get_batch_processing_metrics(start_datetime, end_datetime)
        
        if metrics and metrics.get('total_sessions', 0) > 0:
            # Key metrics cards
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Total Sessions", metrics.get('total_sessions', 0))
            with col2:
                st.metric("Files Processed", metrics.get('total_files_processed', 0))
            with col3:
                avg_time = metrics.get('avg_processing_time', 0)
                st.metric("Avg Processing Time", f"{avg_time:.2f}s" if avg_time else "N/A")
            with col4:
                success_files = metrics.get('total_success_files', 0)
                total_files = metrics.get('total_files_processed', 0)
                success_rate = success_files / total_files * 100 if total_files > 0 else 0
                st.metric("Success Rate", f"{success_rate:.1f}%")
            
            # Processing timeline chart
            timeline_data = db_integration.get_processing_timeline(start_datetime, end_datetime)
            
            if timeline_data:
                timeline_df = pd.DataFrame(timeline_data)
                timeline_df['date'] = pd.to_datetime(timeline_df['date'])
                
                fig = px.line(
                    timeline_df, 
                    x='date', 
                    y='files_processed', 
                    title='Daily Processing Volume',
                    markers=True
                )
                fig.update_layout(xaxis_title="Date", yaxis_title="Files Processed")
                st.plotly_chart(fig, use_container_width=True)
            
            # Performance distribution
            perf_data = db_integration.get_performance_distribution(start_datetime, end_datetime)
            
            if perf_data:
                perf_df = pd.DataFrame(perf_data)
                fig2 = px.histogram(
                    perf_df, 
                    x='processing_time', 
                    title='Processing Time Distribution',
                    nbins=30
                )
                fig2.update_layout(xaxis_title="Processing Time (seconds)", yaxis_title="Count")
                st.plotly_chart(fig2, use_container_width=True)
        
        else:
            st.info("No processing data available for the selected time range")


def show_recent_results(db_integration: ANPRDatabaseIntegration):
    """Show recent processing results."""
    st.subheader("📋 Recent Results")
    
    # Get current session results
    current_session = db_integration.get_current_batch_session_status()
    
    if current_session:
        session_id = current_session['session_id']
        results = db_integration.get_session_results(session_id, limit=50)
        
        if results:
            # Convert to DataFrame for better display
            results_df = pd.DataFrame([
                {
                    'File': os.path.basename(r['file_path']),
                    'Folder': r['folder_name'],
                    'Plate': r['plate_text'] or 'None',
                    'Confidence': f"{r['confidence']:.3f}" if r['confidence'] else 'N/A',
                    'Processing Time': f"{r['processing_time']:.2f}s",
                    'Status': '✅' if r['status'] == 'SUCCESS' else '❌',
                    'Timestamp': datetime.fromisoformat(r['timestamp']).strftime('%H:%M:%S')
                }
                for r in results
            ])
            
            st.dataframe(results_df, use_container_width=True)
            
            # Download results as CSV
            csv = results_df.to_csv(index=False)
            st.download_button(
                label="📥 Download Results CSV",
                data=csv,
                file_name=f"batch_results_{session_id[:8]}.csv",
                mime="text/csv"
            )
        else:
            st.info("No results available yet")
    else:
        st.info("No active session - start batch processing to see results")


def show_realtime_log(placeholder, session_id: str):
    """Show real-time processing log."""
    try:
        # This would ideally connect to a real-time log stream
        # For now, we'll show recent results updates
        
        with placeholder.container():
            db = get_db()
            db_integration = ANPRDatabaseIntegration(db)
            
            # Get the latest 10 results
            recent_results = db_integration.get_session_results(session_id, limit=10, offset=0)
            
            if recent_results:
                log_text = "**Latest Processing Updates:**\n"
                for result in reversed(recent_results):  # Show newest first
                    timestamp = datetime.fromisoformat(result['timestamp']).strftime('%H:%M:%S')
                    file_name = os.path.basename(result['file_path'])
                    status = '✅' if result['status'] == 'SUCCESS' else '❌'
                    plate = result['plate_text'] or 'No plate detected'
                    
                    log_text += f"`{timestamp}` {status} {file_name} - {plate}\n"
                
                st.markdown(log_text)
            else:
                st.info("No recent activity")
                
        # Auto-refresh every 5 seconds if session is running
        time.sleep(5)
        st.rerun()
        
    except Exception as e:
        placeholder.error(f"Error loading log: {e}")


def show_directory_performance():
    """Show performance statistics by directory."""
    st.subheader("📁 Directory Performance")
    
    db = get_db()
    db_integration = ANPRDatabaseIntegration(db)
    
    # Time range
    start_date = datetime.now() - timedelta(days=7)
    end_date = datetime.now()
    
    dir_stats = db_integration.get_directory_performance_stats(start_date, end_date)
    
    if dir_stats:
        dir_df = pd.DataFrame([
            {
                'Directory': stat['folder_name'],
                'Total Files': stat['total_files'],
                'Avg Processing Time': f"{stat['avg_processing_time']:.2f}s",
                'Success Count': stat['success_count'],
                'Error Count': stat['error_count'],
                'Success Rate': f"{stat['success_rate']:.1%}"
            }
            for stat in dir_stats
        ])
        
        st.dataframe(dir_df, use_container_width=True)
    else:
        st.info("No directory performance data available")