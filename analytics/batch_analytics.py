import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
import json

from db import get_db, ANPRDatabaseIntegration


class BatchAnalytics:
    """Advanced analytics for batch processing operations."""
    
    def __init__(self):
        self.db = get_db()
        self.db_integration = ANPRDatabaseIntegration(self.db)
    
    def show_batch_analytics(self):
        """Main analytics dashboard."""
        st.title("📊 Batch Processing Analytics")
        
        # Time range selector
        col1, col2, col3 = st.columns([2, 2, 1])
        with col1:
            start_date = st.date_input(
                "Start Date", 
                datetime.now() - timedelta(days=30),
                max_value=datetime.now().date()
            )
        with col2:
            end_date = st.date_input(
                "End Date", 
                datetime.now(),
                max_value=datetime.now().date()
            )
        with col3:
            refresh_data = st.button("🔄 Refresh Data")
        
        if start_date <= end_date:
            start_datetime = datetime.combine(start_date, datetime.min.time())
            end_datetime = datetime.combine(end_date, datetime.max.time())
            
            # Get comprehensive metrics
            metrics = self.db_integration.get_batch_processing_metrics(start_datetime, end_datetime)
            
            if metrics and metrics.get('total_sessions', 0) > 0:
                self._show_overview_metrics(metrics)
                self._show_processing_timeline(start_datetime, end_datetime)
                self._show_performance_analysis(start_datetime, end_datetime)
                self._show_directory_analysis(start_datetime, end_datetime)
                self._show_system_performance(start_datetime, end_datetime)
                self._show_trend_analysis(start_datetime, end_datetime)
            else:
                st.info(f"No batch processing data available for the period {start_date} to {end_date}")
                st.markdown("""
                **To see analytics:**
                1. Run some batch processing sessions
                2. Wait for processing to complete
                3. Return to this dashboard
                """)
        else:
            st.error("Start date must be before end date")
    
    def _show_overview_metrics(self, metrics: Dict[str, Any]):
        """Show high-level overview metrics."""
        st.subheader("📈 Overview Metrics")
        
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1:
            total_sessions = metrics.get('total_sessions', 0)
            st.metric("Total Sessions", total_sessions)
        
        with col2:
            total_files = metrics.get('total_files_processed', 0)
            st.metric("Files Processed", f"{total_files:,}")
        
        with col3:
            success_files = metrics.get('total_success_files', 0)
            error_files = metrics.get('total_error_files', 0)
            success_rate = (success_files / total_files * 100) if total_files > 0 else 0
            st.metric("Success Rate", f"{success_rate:.1f}%")
        
        with col4:
            avg_time = metrics.get('avg_processing_time', 0)
            st.metric("Avg Processing Time", f"{avg_time:.2f}s" if avg_time else "N/A")
        
        with col5:
            avg_duration = metrics.get('avg_session_duration_minutes', 0)
            st.metric("Avg Session Duration", f"{avg_duration:.1f}min" if avg_duration else "N/A")
        
        # Additional derived metrics
        if total_files > 0 and avg_time > 0:
            col1, col2, col3 = st.columns(3)
            
            with col1:
                throughput = 60 / avg_time if avg_time > 0 else 0
                st.metric("Estimated Throughput", f"{throughput:.1f} files/min")
            
            with col2:
                st.metric("Success Count", f"{success_files:,}")
            
            with col3:
                st.metric("Error Count", f"{error_files:,}")
    
    def _show_processing_timeline(self, start_date: datetime, end_date: datetime):
        """Show processing timeline with trends."""
        st.subheader("📅 Processing Timeline")
        
        timeline_data = self.db_integration.get_processing_timeline(start_date, end_date)
        
        if timeline_data:
            df = pd.DataFrame(timeline_data)
            df['date'] = pd.to_datetime(df['date'])
            
            # Create multi-line chart
            fig = make_subplots(
                rows=2, cols=1,
                subplot_titles=('Files Processed Over Time', 'Session Count and Success Rate'),
                vertical_spacing=0.12
            )
            
            # Files processed timeline
            fig.add_trace(
                go.Scatter(
                    x=df['date'], 
                    y=df['files_processed'],
                    mode='lines+markers',
                    name='Files Processed',
                    line=dict(color='#3498db', width=3),
                    marker=dict(size=6)
                ),
                row=1, col=1
            )
            
            # Sessions count
            fig.add_trace(
                go.Bar(
                    x=df['date'], 
                    y=df['sessions_count'],
                    name='Sessions',
                    marker_color='#e74c3c',
                    opacity=0.7
                ),
                row=2, col=1
            )
            
            # Success rate line
            if 'files_success' in df.columns:
                df['success_rate'] = df['files_success'] / df['files_processed'] * 100
                fig.add_trace(
                    go.Scatter(
                        x=df['date'], 
                        y=df['success_rate'],
                        mode='lines+markers',
                        name='Success Rate (%)',
                        line=dict(color='#27ae60', width=2),
                        yaxis='y2'
                    ),
                    row=2, col=1
                )
            
            fig.update_layout(
                height=600,
                title_text="Processing Activity Over Time",
                showlegend=True
            )
            
            fig.update_xaxes(title_text="Date", row=2, col=1)
            fig.update_yaxes(title_text="Files", row=1, col=1)
            fig.update_yaxes(title_text="Sessions", row=2, col=1)
            
            st.plotly_chart(fig, use_container_width=True)
            
            # Show data table
            with st.expander("📋 View Raw Data"):
                st.dataframe(df.sort_values('date', ascending=False))
    
    def _show_performance_analysis(self, start_date: datetime, end_date: datetime):
        """Show detailed performance analysis."""
        st.subheader("⚡ Performance Analysis")
        
        perf_data = self.db_integration.get_performance_distribution(start_date, end_date)
        
        if perf_data:
            df = pd.DataFrame(perf_data)
            
            col1, col2 = st.columns(2)
            
            with col1:
                # Processing time distribution
                fig1 = px.histogram(
                    df, 
                    x='processing_time', 
                    title='Processing Time Distribution',
                    nbins=50,
                    color_discrete_sequence=['#3498db']
                )
                fig1.update_layout(
                    xaxis_title="Processing Time (seconds)",
                    yaxis_title="Count",
                    bargap=0.1
                )
                st.plotly_chart(fig1, use_container_width=True)
            
            with col2:
                # Processing time by folder
                if 'folder_name' in df.columns:
                    fig2 = px.box(
                        df, 
                        x='folder_name', 
                        y='processing_time',
                        title='Processing Time by Directory',
                        color_discrete_sequence=['#e74c3c']
                    )
                    fig2.update_layout(
                        xaxis_title="Directory",
                        yaxis_title="Processing Time (seconds)",
                        xaxis={'categoryorder': 'total descending'}
                    )
                    st.plotly_chart(fig2, use_container_width=True)
            
            # Performance statistics
            st.markdown("#### 📊 Performance Statistics")
            stats_col1, stats_col2, stats_col3, stats_col4 = st.columns(4)
            
            processing_times = df['processing_time']
            
            with stats_col1:
                st.metric("Median Time", f"{processing_times.median():.2f}s")
            with stats_col2:
                st.metric("90th Percentile", f"{processing_times.quantile(0.9):.2f}s")
            with stats_col3:
                st.metric("95th Percentile", f"{processing_times.quantile(0.95):.2f}s")
            with stats_col4:
                st.metric("Max Time", f"{processing_times.max():.2f}s")
    
    def _show_directory_analysis(self, start_date: datetime, end_date: datetime):
        """Show analysis by directory."""
        st.subheader("📁 Directory Performance Analysis")
        
        dir_stats = self.db_integration.get_directory_performance_stats(start_date, end_date)
        
        if dir_stats:
            df = pd.DataFrame(dir_stats)
            
            # Sort by total files
            df = df.sort_values('total_files', ascending=False)
            
            col1, col2 = st.columns(2)
            
            with col1:
                # Files processed by directory
                fig1 = px.bar(
                    df.head(10), 
                    x='total_files', 
                    y='folder_name',
                    orientation='h',
                    title='Top 10 Directories by Files Processed',
                    color='success_rate',
                    color_continuous_scale='RdYlGn'
                )
                fig1.update_layout(
                    xaxis_title="Total Files",
                    yaxis_title="Directory",
                    yaxis={'categoryorder': 'total ascending'}
                )
                st.plotly_chart(fig1, use_container_width=True)
            
            with col2:
                # Success rate by directory
                fig2 = px.scatter(
                    df, 
                    x='total_files', 
                    y='success_rate',
                    size='avg_processing_time',
                    hover_data=['folder_name', 'success_count', 'error_count'],
                    title='Success Rate vs Volume',
                    color='avg_processing_time',
                    color_continuous_scale='viridis'
                )
                fig2.update_layout(
                    xaxis_title="Total Files",
                    yaxis_title="Success Rate",
                    yaxis=dict(tickformat='.1%')
                )
                st.plotly_chart(fig2, use_container_width=True)
            
            # Directory performance table
            st.markdown("#### 📋 Directory Performance Details")
            
            display_df = df.copy()
            display_df['Success Rate'] = display_df['success_rate'].apply(lambda x: f"{x:.1%}")
            display_df['Avg Processing Time'] = display_df['avg_processing_time'].apply(lambda x: f"{x:.2f}s")
            
            display_cols = {
                'folder_name': 'Directory',
                'total_files': 'Total Files',
                'Success Rate': 'Success Rate',
                'Avg Processing Time': 'Avg Time',
                'success_count': 'Successes',
                'error_count': 'Errors'
            }
            
            st.dataframe(
                display_df[list(display_cols.keys())].rename(columns=display_cols),
                use_container_width=True
            )
    
    def _show_system_performance(self, start_date: datetime, end_date: datetime):
        """Show system performance metrics."""
        st.subheader("🖥️ System Performance")
        
        # This would typically query performance metrics from the database
        # For now, we'll show placeholder information
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### CPU & Memory Usage")
            st.info("System performance monitoring data would be displayed here when available")
            
            # Placeholder chart
            sample_data = pd.DataFrame({
                'time': pd.date_range(start=start_date, end=end_date, freq='H'),
                'cpu_percent': np.random.uniform(20, 80, len(pd.date_range(start=start_date, end=end_date, freq='H'))),
                'memory_percent': np.random.uniform(30, 70, len(pd.date_range(start=start_date, end=end_date, freq='H')))
            })
            
            fig = px.line(
                sample_data.melt(id_vars=['time'], var_name='metric', value_name='percent'),
                x='time', y='percent', color='metric',
                title='System Resource Usage Over Time'
            )
            fig.update_layout(yaxis_title="Usage (%)")
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            st.markdown("#### GPU Utilization")
            st.info("GPU performance data would be displayed here when available")
            
            # Placeholder GPU data
            gpu_data = pd.DataFrame({
                'GPU': ['GPU 0', 'GPU 1', 'GPU 2', 'GPU 3'],
                'Avg Utilization': [75.2, 68.9, 82.1, 59.4],
                'Peak Utilization': [95.1, 88.7, 96.3, 78.2]
            })
            
            fig2 = px.bar(
                gpu_data.melt(id_vars=['GPU'], var_name='metric', value_name='utilization'),
                x='GPU', y='utilization', color='metric', barmode='group',
                title='GPU Utilization Summary'
            )
            fig2.update_layout(yaxis_title="Utilization (%)")
            st.plotly_chart(fig2, use_container_width=True)
    
    def _show_trend_analysis(self, start_date: datetime, end_date: datetime):
        """Show trend analysis and predictions."""
        st.subheader("📈 Trend Analysis")
        
        timeline_data = self.db_integration.get_processing_timeline(start_date, end_date)
        
        if timeline_data and len(timeline_data) > 2:
            df = pd.DataFrame(timeline_data)
            df['date'] = pd.to_datetime(df['date'])
            df = df.sort_values('date')
            
            col1, col2 = st.columns(2)
            
            with col1:
                # Processing volume trend
                fig1 = px.scatter(
                    df, x='date', y='files_processed',
                    trendline='ols',
                    title='Processing Volume Trend',
                    color_discrete_sequence=['#3498db']
                )
                fig1.update_layout(
                    xaxis_title="Date",
                    yaxis_title="Files Processed"
                )
                st.plotly_chart(fig1, use_container_width=True)
                
                # Calculate trend
                if len(df) > 1:
                    recent_avg = df['files_processed'].tail(3).mean()
                    early_avg = df['files_processed'].head(3).mean()
                    trend = ((recent_avg - early_avg) / early_avg * 100) if early_avg > 0 else 0
                    
                    trend_color = "green" if trend > 0 else "red" if trend < 0 else "gray"
                    trend_icon = "📈" if trend > 0 else "📉" if trend < 0 else "➡️"
                    
                    st.markdown(f"""
                    **Volume Trend:** {trend_icon} {trend:+.1f}% 
                    <span style="color: {trend_color}">
                    ({recent_avg:.0f} vs {early_avg:.0f} files/day average)
                    </span>
                    """, unsafe_allow_html=True)
            
            with col2:
                # Success rate trend
                if 'files_success' in df.columns:
                    df['success_rate'] = df['files_success'] / df['files_processed'] * 100
                    
                    fig2 = px.scatter(
                        df, x='date', y='success_rate',
                        trendline='ols',
                        title='Success Rate Trend',
                        color_discrete_sequence=['#27ae60']
                    )
                    fig2.update_layout(
                        xaxis_title="Date",
                        yaxis_title="Success Rate (%)"
                    )
                    st.plotly_chart(fig2, use_container_width=True)
                    
                    # Success rate analysis
                    recent_success = df['success_rate'].tail(3).mean()
                    early_success = df['success_rate'].head(3).mean()
                    success_trend = recent_success - early_success
                    
                    success_color = "green" if success_trend > 0 else "red" if success_trend < 0 else "gray"
                    success_icon = "📈" if success_trend > 0 else "📉" if success_trend < 0 else "➡️"
                    
                    st.markdown(f"""
                    **Success Rate Trend:** {success_icon} {success_trend:+.1f}% 
                    <span style="color: {success_color}">
                    ({recent_success:.1f}% vs {early_success:.1f}% average)
                    </span>
                    """, unsafe_allow_html=True)
            
            # Weekly patterns
            if len(df) > 7:
                st.markdown("#### 📅 Weekly Patterns")
                df['day_of_week'] = df['date'].dt.day_name()
                
                weekly_stats = df.groupby('day_of_week').agg({
                    'files_processed': 'mean',
                    'sessions_count': 'mean'
                }).round(1)
                
                # Reorder days
                day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
                weekly_stats = weekly_stats.reindex([d for d in day_order if d in weekly_stats.index])
                
                fig3 = px.bar(
                    weekly_stats.reset_index(), 
                    x='day_of_week', 
                    y='files_processed',
                    title='Average Files Processed by Day of Week',
                    color_discrete_sequence=['#9b59b6']
                )
                fig3.update_layout(
                    xaxis_title="Day of Week",
                    yaxis_title="Average Files Processed"
                )
                st.plotly_chart(fig3, use_container_width=True)
        
        else:
            st.info("Not enough data points for trend analysis. Please run more batch processing sessions.")


def show_batch_analytics():
    """Show the batch analytics dashboard."""
    analytics = BatchAnalytics()
    analytics.show_batch_analytics()