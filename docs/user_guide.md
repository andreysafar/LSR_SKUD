# LSR_SKUD User Guide

## Table of Contents

1. [Getting Started](#getting-started)
2. [Web Interface Overview](#web-interface-overview)
3. [Live Recognition](#live-recognition)
4. [Batch Processing](#batch-processing)
5. [Analytics](#analytics)
6. [System Management](#system-management)
7. [Troubleshooting](#troubleshooting)
8. [Advanced Features](#advanced-features)

## Getting Started

### System Overview

LSR_SKUD is a comprehensive license plate recognition and access control system that combines:
- **Live camera recognition** for real-time access control
- **High-performance batch processing** for video archive analysis
- **Advanced analytics** for usage patterns and performance monitoring
- **Telegram bot integration** for notifications and management

### First-Time Setup

#### 1. Access the System
Navigate to the web interface (default: http://localhost:8501)

#### 2. Initial Configuration
The system will guide you through initial setup:
- Configure cameras for live recognition
- Set up video archive paths for batch processing
- Configure Telegram bot (optional)
- Set recognition thresholds

#### 3. Model Verification
Ensure recognition models are loaded:
- Navigate to Settings → Models
- Verify model status indicators are green
- Download missing models if needed

## Web Interface Overview

### Navigation

The main navigation is located in the sidebar:

```
🏠 Dashboard      - System overview and live status
📹 Live Recognition - Real-time camera monitoring
🔄 Batch Processing - Archive video processing
👥 User Management - Access control management
🎯 Training       - Model training and improvement
📊 Analytics      - Performance and usage analytics  
⚙️ Settings       - System configuration
```

### Dashboard Elements

#### System Status Cards
- **Registered Users**: Total users in the system
- **Active Passes**: Currently valid access passes
- **Cameras Online**: Camera connectivity status
- **Pending Reviews**: Items requiring manual review

#### Activity Overview
- **Today's Activity**: Daily processing statistics
- **Recent Recognition Events**: Latest plate detections
- **Camera Status**: Real-time camera health
- **Training Status**: Model training progress

## Live Recognition

### Overview
Live recognition processes real-time camera feeds to identify vehicles and license plates for access control.

### Setting Up Cameras

#### 1. Add Camera
1. Navigate to **Settings** → **Cameras**
2. Click **Add Camera**
3. Enter camera details:
   - **Name**: Descriptive camera name
   - **Stream URL**: RTSP or HTTP stream URL
   - **Gate Device**: Associated gate controller
   - **Recognition Zone**: Area mask (optional)

#### 2. Configure Recognition
- **Vehicle Confidence**: Minimum confidence for vehicle detection (0.1-1.0)
- **Plate Confidence**: Minimum confidence for plate detection (0.1-1.0)
- **Processing Interval**: Time between recognition attempts (seconds)

#### 3. Test Camera
Use the **Test Camera** feature to verify:
- Stream connectivity
- Recognition accuracy
- Response time

### Managing Recognition Events

#### Viewing Events
Navigate to **📹 Live Recognition** to see:
- **Active Camera Feeds**: Live video streams (if available)
- **Recent Detections**: Latest recognition results
- **Recognition History**: Searchable event log

#### Event Details
Each event shows:
- **Timestamp**: When the detection occurred
- **Camera**: Which camera detected the plate
- **Plate Number**: Recognized license plate text
- **Confidence**: Recognition confidence score
- **Vehicle Image**: Captured vehicle photo
- **Action Taken**: Gate opened/access denied

#### Manual Review
For low-confidence detections:
1. Click on the event in the history
2. Review the captured image
3. Correct the plate number if needed
4. Mark as **Approved** or **Rejected**

## Batch Processing

### Overview
Batch processing analyzes video archives to extract license plate information from historical footage.

### Starting Batch Processing

#### 1. Configure Processing Job
Navigate to **🔄 Batch Processing** and set:

**Input Settings:**
- **Input Directories**: Paths to video archives (one per line)
  ```
  /mnt/iss_media/CAM_14
  /mnt/iss_media/CAM_16
  /mnt/iss_media/CAM_18
  ```
- **Video Extension**: File format (.issvd, .mp4, .avi, etc.)

**Worker Configuration:**
- **CPU Workers**: Number of CPU threads for video conversion (1-16)
- **GPU Workers**: Number of GPU threads for recognition (1-8)
- **FFmpeg GPU Workers**: GPU threads for video processing (0-4)

**Processing Settings:**
- **Confidence Threshold**: Minimum confidence for detections (0.1-1.0)
- **Frame Skip**: Process every N frames (1-20)
- **Timeout**: Maximum processing time per job (10-180 minutes)

#### 2. Start Processing
1. Click **🚀 Start Batch Processing**
2. Monitor progress in real-time
3. View processing logs for details

#### 3. Monitor Progress
The interface shows:
- **Status**: Current processing state
- **Progress**: Files processed vs. total
- **Processing Rate**: Files per minute
- **ETA**: Estimated time to completion
- **Success Rate**: Percentage of successful processing

### Processing Results

#### Real-Time Monitoring
Watch the **Live Processing Log** to see:
- Files being processed
- Success/failure status
- Detected license plates
- Processing times

#### Results Export
- **Download CSV**: Export all results to spreadsheet
- **View Images**: Browse captured vehicle images
- **Filter Results**: Search by camera, date, plate number

#### Session History
View previous batch processing sessions:
- **Session Details**: Configuration and results
- **Performance Metrics**: Processing speed and accuracy
- **Error Analysis**: Failed files and reasons

## Analytics

### Overview
The analytics dashboard provides insights into system performance and usage patterns.

### Performance Metrics

#### Overview Cards
- **Total Sessions**: Number of batch processing jobs
- **Files Processed**: Total files analyzed
- **Average Processing Time**: Performance per file
- **Success Rate**: Percentage of successful processing

#### Timeline Charts
- **Daily Processing Volume**: Files processed over time
- **Session Count**: Number of processing jobs per day
- **Success Rate Trends**: Quality metrics over time

#### Performance Analysis
- **Processing Time Distribution**: Histogram of processing speeds
- **Performance by Directory**: Compare different camera locations
- **System Resource Usage**: CPU, memory, and GPU utilization

### Directory Analysis

#### Performance by Location
- **Files per Directory**: Processing volume by camera
- **Success Rates**: Quality by camera location
- **Processing Speed**: Performance comparison
- **Error Analysis**: Common issues by directory

#### Usage Patterns
- **Peak Processing Times**: When system is most active
- **Weekly Patterns**: Day-of-week analysis
- **Seasonal Trends**: Long-term usage patterns

### System Performance

#### Resource Utilization
- **CPU Usage**: Processing load over time
- **Memory Usage**: System memory consumption
- **GPU Utilization**: Graphics card usage
- **Disk I/O**: Storage performance

#### Performance Optimization
Use analytics to:
- **Identify Bottlenecks**: Find performance limitations
- **Optimize Settings**: Adjust worker counts
- **Plan Upgrades**: Determine hardware needs
- **Schedule Processing**: Avoid peak usage times

## System Management

### User Management

#### Adding Users
1. Navigate to **👥 User Management**
2. Click **Add User**
3. Enter user details:
   - Name and contact information
   - License plate numbers
   - Access permissions
   - Validity period

#### Managing Access Passes
- **Active Passes**: Currently valid access
- **Expired Passes**: Past access grants
- **Temporary Passes**: Time-limited access
- **Bulk Import**: CSV import for multiple users

### Training Data Management

#### Collecting Training Data
Navigate to **🎯 Training** to:
- **Review Detections**: Verify accuracy
- **Correct Errors**: Fix misidentified plates
- **Add Samples**: Contribute to training dataset
- **Export Training Data**: Download for external training

#### Model Training
- **Automatic Training**: System learns from corrections
- **Manual Training**: Trigger training sessions
- **Model Versioning**: Track model improvements
- **A/B Testing**: Compare model performance

### System Settings

#### General Settings
- **System Name**: Installation identifier
- **Time Zone**: Local time configuration
- **Language**: Interface language
- **Theme**: Dark/light mode

#### Recognition Settings
- **Default Thresholds**: System-wide confidence levels
- **Processing Limits**: Maximum resource usage
- **Storage Retention**: Data cleanup policies
- **Notification Settings**: Alert configurations

#### Integration Settings
- **Telegram Bot**: Bot token and permissions
- **Parsec Integration**: Access control system
- **External APIs**: Third-party integrations
- **Backup Configuration**: Data protection

## Troubleshooting

### Common Issues

#### Low Recognition Accuracy
**Symptoms**: Many false positives or missed detections
**Solutions**:
1. Adjust confidence thresholds in settings
2. Check camera positioning and image quality
3. Clean camera lenses
4. Review lighting conditions
5. Consider retraining models

#### Slow Processing Speed
**Symptoms**: Batch processing takes too long
**Solutions**:
1. Reduce number of workers if system is overloaded
2. Increase workers if system has unused capacity
3. Check available GPU memory
4. Verify sufficient disk space
5. Monitor system resources in analytics

#### Camera Connection Issues
**Symptoms**: Camera shows offline or no video
**Solutions**:
1. Verify network connectivity
2. Check camera credentials
3. Test stream URL manually
4. Restart camera if needed
5. Check firewall settings

#### Out of Disk Space
**Symptoms**: Processing fails or system errors
**Solutions**:
1. Clean old snapshots in data/snapshots/
2. Remove old log files
3. Archive old batch processing results
4. Increase storage capacity
5. Configure automatic cleanup

### Performance Optimization

#### Hardware Optimization
- **CPU**: More cores improve batch processing speed
- **RAM**: More memory allows larger batch sizes
- **GPU**: Dedicated GPU significantly improves speed
- **Storage**: SSD storage improves I/O performance

#### Configuration Optimization
- **Worker Counts**: Balance based on hardware
- **Confidence Thresholds**: Higher values reduce false positives
- **Frame Skip**: Higher values process faster but may miss detections
- **Batch Sizes**: Larger batches more efficient but use more memory

### Getting Help

#### Log Files
Check these locations for diagnostic information:
- **Application Logs**: Available in web interface
- **Batch Processing Logs**: `batch_processing/logs/`
- **System Logs**: Docker/Kubernetes logs
- **Database Logs**: SQLite error logs

#### Support Information
When requesting support, provide:
- System configuration (hardware, OS)
- Error messages or screenshots
- Relevant log entries
- Steps to reproduce the issue
- Expected vs. actual behavior

## Advanced Features

### API Access

#### REST API
Access system functions programmatically:
- **GET /api/status**: System status
- **POST /api/recognition**: Submit image for recognition
- **GET /api/results**: Retrieve processing results
- **POST /api/batch**: Start batch processing job

#### WebSocket Interface
Real-time updates for:
- Live recognition events
- Batch processing progress
- System status changes
- Performance metrics

### Custom Integrations

#### Webhook Configuration
Set up webhooks for:
- Recognition events
- System alerts
- Processing completion
- User access events

#### External Database Integration
Connect to external databases for:
- User management
- Access logging
- Reporting systems
- Backup storage

### Advanced Configuration

#### Environment Variables
Customize system behavior with environment variables:
```bash
# Performance tuning
ANPR_CPU_WORKERS=8
ANPR_GPU_WORKERS=4
TORCHSCRIPT_ENABLED=true

# Processing options
ANPR_CONFIDENCE_THRESHOLD=0.3
ANPR_FRAME_SKIP=5
HALF_PRECISION=true

# Output configuration
ANPR_OUTPUT_CSV_PATH=custom/path.csv
ANPR_OUTPUT_IMAGES_DIR=custom/images/
```

#### Configuration Files
Advanced users can customize:
- Model parameters
- Processing pipelines
- Database schemas
- UI themes

### Automation

#### Scheduled Processing
Set up automatic batch processing:
- **Cron Jobs**: Regular processing schedules
- **Event Triggers**: Process when new files appear
- **API Scheduling**: Programmatic job control
- **Resource Scheduling**: Process during off-peak hours

#### Automatic Cleanup
Configure automatic maintenance:
- **Log Rotation**: Limit log file sizes
- **Data Archival**: Move old results to archive
- **Temporary File Cleanup**: Remove processing artifacts
- **Database Optimization**: Regular database maintenance

This user guide provides comprehensive information for operating LSR_SKUD effectively. For additional support or advanced configuration, consult the technical documentation or contact system administrators.