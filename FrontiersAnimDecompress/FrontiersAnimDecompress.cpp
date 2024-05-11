#include <vector>
#include <string>
#include <sstream>
#include <ostream>
#include <iostream>
#include <fstream>

#include "acl/compression/compress.h"
#include "acl/compression/compression_settings.h"
#include "acl/compression/output_stats.h"
#include "acl/compression/track_array.h"
#include "acl/core/ansi_allocator.h"
#include "acl/decompression/decompress.h"
#include "acl/decompression/decompression_settings.h"

using namespace acl;

struct vector
{
	float x, y, z;
};

struct quat
{
	float x, y, z, w;
};

struct frontiers_writer final : public track_writer
{
	explicit frontiers_writer(std::vector<rtm::qvvf>& Transforms_) : Transforms(Transforms_) {}

	std::vector<rtm::qvvf>& Transforms;

	//////////////////////////////////////////////////////////////////////////
	// Called by the decoder to write out a quaternion rotation value for a specified bone index.
	void RTM_SIMD_CALL write_rotation(uint32_t TrackIndex, rtm::quatf_arg0 Rotation)
	{
		Transforms[TrackIndex].rotation = Rotation;
	}

	//////////////////////////////////////////////////////////////////////////
	// Called by the decoder to write out a translation value for a specified bone index.
	void RTM_SIMD_CALL write_translation(uint32_t TrackIndex, rtm::vector4f_arg0 Translation)
	{
		Transforms[TrackIndex].translation = Translation;
	}

	//////////////////////////////////////////////////////////////////////////
	// Called by the decoder to write out a scale value for a specified bone index.
	void RTM_SIMD_CALL write_scale(uint32_t TrackIndex, rtm::vector4f_arg0 Scale)
	{
		Transforms[TrackIndex].scale = Scale;
	}
};

struct anim_output
{
	float sample_rate;
	float duration;
	uint32_t frame_count;
	uint32_t bone_count;
	std::vector<std::vector<rtm::qvvf>> all_tracks;
};

struct python_buffer
{
	unsigned char* data_buffer;
	size_t data_buffer_size;
};

extern "C" __declspec(dllexport) python_buffer decompress(const char* buffer_in)
{
	decompression_context<default_transform_decompression_settings> context;
	error_result result;

	const compressed_tracks* compressed_anim = make_compressed_tracks(buffer_in, &result);

	if (!context.initialize(*compressed_anim))
	{
		std::cout << "Failed to read animation file" << result.c_str() << std::endl;
		python_buffer fail;
		fail.data_buffer = nullptr;
		fail.data_buffer_size = 0;
		return fail;
	}

	std::vector<rtm::qvvf> raw_local_pose_transforms;

	for (uint32_t i = 0; i < compressed_anim->get_num_tracks(); i++)
	{
		raw_local_pose_transforms.push_back(rtm::qvvf());
	}

	frontiers_writer writer(raw_local_pose_transforms);

	std::vector<std::vector<rtm::qvvf>> all_tracks;

	for (uint32_t sample_index = 0; sample_index < compressed_anim->get_num_samples_per_track(); ++sample_index)
	{
		const float sample_time = rtm::scalar_min(float(sample_index) / compressed_anim->get_sample_rate(), compressed_anim->get_duration());

		context.seek(sample_time, acl::sample_rounding_policy::none);
		context.decompress_tracks(writer);
		all_tracks.push_back(writer.Transforms);
	}

	anim_output output;

	output.duration = compressed_anim->get_duration();
	output.sample_rate = compressed_anim->get_sample_rate();
	output.frame_count = compressed_anim->get_num_samples_per_track();
	output.bone_count = compressed_anim->get_num_tracks();
	output.all_tracks = all_tracks;

	// String to hold data instead of file
	std::ostringstream data_string(std::ios::binary);

	data_string.write((char*)&output.duration, sizeof(float));
	data_string.write((char*)&output.sample_rate, sizeof(float));
	data_string.write((char*)&output.frame_count, sizeof(uint32_t));
	data_string.write((char*)&output.bone_count, sizeof(uint32_t));

	for (uint32_t i = 0; i < output.all_tracks.size(); i++)
	{
		data_string.write((char*)output.all_tracks[i].data(), sizeof rtm::qvvf * output.all_tracks[i].size());
	}

	std::string binary_string = data_string.str();
	size_t buffer_out_size = binary_string.size();

	unsigned char* buffer_out = new unsigned char[buffer_out_size];

	std::copy(binary_string.begin(), binary_string.end(), buffer_out);

	python_buffer python_out;

	python_out.data_buffer = buffer_out;
	python_out.data_buffer_size = buffer_out_size;

	return python_out;
}

#pragma optimize("", off) 
track_array_qvvf load_tracks(const char*& buffer, ansi_allocator& allocator, uint32_t sample_count, float sample_rate, uint32_t track_count)
{
	track_array_qvvf raw_track_list(allocator, track_count);

	for (uint32_t i = 0; i < track_count; i++)
	{
		std::vector<rtm::qvvf> track;
		for (uint32_t j = 0; j < sample_count; j++)
		{
			uint32_t file_pos = 0x10 + j * track_count * sizeof rtm::qvvf + i * sizeof rtm::qvvf;
			rtm::qvvf transform = *(rtm::qvvf*)&buffer[file_pos];
			track.push_back(transform);
		}

		track_desc_transformf desc;
		desc.output_index = i;
		desc.precision = 0.001f;
		desc.shell_distance = 3.f;
		track_qvvf raw_track = track_qvvf::make_reserve(desc, allocator, sample_count, sample_rate);
		for (uint32_t j = 0; j < sample_count; j++)
		{
			raw_track[j] = track[j];
		}
		raw_track_list[i] = std::move(raw_track);
	}
	return raw_track_list;
}
#pragma optimize("", on) 
extern "C" __declspec(dllexport) python_buffer compress(const char* buffer_in)
{
	ansi_allocator allocator;

	float duration = *(float*)&buffer_in[0];
	float sample_rate = *(float*)&buffer_in[4];
	uint32_t sample_count = *(uint32_t*)&buffer_in[8];
	uint32_t track_count = *(uint32_t*)&buffer_in[0xC];

	track_array_qvvf raw_track_list = load_tracks(buffer_in, allocator, sample_count, sample_rate, track_count);

	compression_settings settings;

	settings.level = compression_level8::highest;
	settings.rotation_format = rotation_format8::quatf_drop_w_variable;
	settings.translation_format = vector_format8::vector3f_variable;
	settings.scale_format = vector_format8::vector3f_variable;

	qvvf_transform_error_metric error_metric;
	settings.error_metric = &error_metric;

	output_stats stats;
	compressed_tracks* out_compressed_tracks = nullptr;
	compressed_tracks* root_out_compressed_tracks = nullptr;

	error_result result = compress_track_list(allocator, raw_track_list, settings, out_compressed_tracks, stats);
	if (out_compressed_tracks == nullptr)
	{
		std::cout << "Failed to compress anim: " << result.c_str() << std::endl;
		python_buffer fail;
		fail.data_buffer = nullptr;
		fail.data_buffer_size = 0;
		return fail;
	}
	
	// String to hold data instead of file
	std::ostringstream data_string(std::ios::binary);

	data_string.write((char*)out_compressed_tracks, out_compressed_tracks->get_size());
	
	std::string binary_string = data_string.str();
	size_t buffer_out_size = binary_string.size();

	unsigned char* buffer_out = new unsigned char[buffer_out_size];

	std::copy(binary_string.begin(), binary_string.end(), buffer_out);

	// std::cout << "Wrote file" << std::endl;

	python_buffer python_out;

	python_out.data_buffer = buffer_out;
	python_out.data_buffer_size = buffer_out_size;

	return python_out;
}

